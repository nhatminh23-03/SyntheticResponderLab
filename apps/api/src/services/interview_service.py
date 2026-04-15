"""Interview service: orchestrates interview batch runs, research brief, and insights.

Data layout:
  - StudySectionState key "interview_synthesis" → interview config (mode, questions, model settings)
  - StudySectionState key "research_brief"      → researcher's brief (primary question, hypotheses, etc.)
  - Job job_type "interview_run"                → batch run result (pairs + grounding report)
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.settings import AppSettings
from src.persistence.models import Job, PersonaPreviewRun, Study, StudySectionState
from src.services.demo_interview_fixtures import ensure_demo_interview_run
from src.services.exceptions import ConflictApiError, ValidationApiError
from src.services.ids import make_public_id
from src.simulation.interview_runner import (
    DEFAULT_MODEL_A,
    DEFAULT_MODEL_B,
    JUDGE_MODEL,
    run_interview_batch as _run_interview_batch,
)
from src.simulation.interview_grounding import score_interview_batch
from src.simulation.interview_prompt_builder import DEFAULT_QUESTIONS, resolve_questions

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RETRIES = 3

INTERVIEW_SECTION_KEYS = ("interview_synthesis", "research_brief")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Section initialisation helpers
# ---------------------------------------------------------------------------

def ensure_interview_sections(session: Session, study: Study) -> None:
    """Create interview section state rows if they don't exist yet."""
    existing_keys = {
        row.section_key
        for row in session.scalars(
            select(StudySectionState).where(StudySectionState.study_id == study.id)
        ).all()
    }
    for key in INTERVIEW_SECTION_KEYS:
        if key not in existing_keys:
            session.add(
                StudySectionState(
                    study_id=study.id,
                    section_key=key,
                    status="not_started",
                    value_json=None,
                    saved_at=None,
                    updated_at=utcnow(),
                )
            )
    session.flush()


# ---------------------------------------------------------------------------
# Interview synthesis config
# ---------------------------------------------------------------------------

def get_interview_synthesis(session: Session, study: Study) -> Dict[str, Any]:
    """Return current interview synthesis config + latest run status."""
    ensure_interview_sections(session, study)
    section = _get_section(session, study, "interview_synthesis")
    latest_run = _latest_interview_job(session, study.id)

    return {
        "status": section.status,
        "value": section.value_json,
        "saved_at": section.saved_at.isoformat() if section.saved_at else None,
        "updated_at": section.updated_at.isoformat() if section.updated_at else None,
        "latest_run": _serialize_interview_job(latest_run) if latest_run else None,
    }


def save_interview_synthesis_config(
    session: Session,
    study: Study,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Save interview synthesis configuration (mode, custom questions, model overrides)."""
    ensure_interview_sections(session, study)
    section = _get_section(session, study, "interview_synthesis")

    # Validate questions if provided
    questions = payload.get("questions")
    if questions is not None:
        if not isinstance(questions, list):
            raise ValidationApiError("questions must be a list of {id, text} objects.")
        for q in questions:
            if not isinstance(q, dict) or not q.get("id") or not q.get("text"):
                raise ValidationApiError("Each question must have 'id' and 'text' fields.")

    section.status = "saved"
    section.value_json = payload
    section.saved_at = section.saved_at or utcnow()
    section.updated_at = utcnow()
    study.updated_at = utcnow()
    session.add(section)
    session.commit()
    session.refresh(study)

    return {
        "status": section.status,
        "value": section.value_json,
        "saved_at": section.saved_at.isoformat() if section.saved_at else None,
        "updated_at": section.updated_at.isoformat() if section.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Interview batch run
# ---------------------------------------------------------------------------

def start_interview_run(
    session: Session,
    settings: AppSettings,
    study: Study,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the full dual-LLM interview batch + STAMP grounding scoring.

    Uses personas from the latest persona preview run.
    Stores results in a Job row with job_type="interview_run".
    """
    ensure_interview_sections(session, study)

    # Resolve configuration
    synthesis_section = _get_section(session, study, "interview_synthesis")
    config = synthesis_section.value_json or {}

    # Get product and audience from saved sections
    sections = {
        row.section_key: row
        for row in session.scalars(
            select(StudySectionState).where(StudySectionState.study_id == study.id)
        ).all()
    }
    product = sections.get("product") and sections["product"].value_json
    audience = sections.get("audience") and sections["audience"].value_json

    # Get latest persona preview
    latest_preview = _get_latest_preview(session, study)
    if not latest_preview or not latest_preview.personas:
        raise ConflictApiError(
            "No persona preview found. Run Personas Preview first before generating interviews."
        )

    # Resolve request parameters
    custom_questions = payload.get("questions") or config.get("questions") or None
    model_a = payload.get("model_a") or config.get("model_a") or DEFAULT_MODEL_A
    model_b = payload.get("model_b") or config.get("model_b") or DEFAULT_MODEL_B
    judge_model = payload.get("judge_model") or config.get("judge_model") or JUDGE_MODEL

    if study.study_mode == "neo_smart":
        demo_job = ensure_demo_interview_run(
            session,
            study,
            latest_preview=latest_preview,
            product=product,
            questions=custom_questions,
        )
        session.commit()
        session.refresh(study)
        return _serialize_interview_job(demo_job)

    api_key = settings.openrouter_api_key or ""
    if not api_key:
        raise ConflictApiError("OPENROUTER_API_KEY is not configured.")

    personas = [p.persona_json for p in sorted(latest_preview.personas, key=lambda x: x.row_index)]

    # Create job record
    job = Job(
        public_id=make_public_id("job"),
        study_id=study.id,
        job_type="interview_run",
        status="running",
        payload_json={
            "persona_count": len(personas),
            "model_a": model_a,
            "model_b": model_b,
            "judge_model": judge_model,
            "custom_questions": bool(custom_questions),
        },
        result_json=None,
        error_json=None,
        queued_at=utcnow(),
        started_at=utcnow(),
    )
    session.add(job)
    session.flush()

    try:
        # Run dual-LLM interviews
        pairs = _run_interview_batch(
            personas=personas,
            questions=custom_questions,
            model_a=model_a,
            model_b=model_b,
            product=product,
            audience=audience,
            api_key=api_key,
        )

        # Score with STAMP grounding
        grounding_report = score_interview_batch(
            pairs=pairs,
            questions=custom_questions,
            product=product,
            api_key=api_key,
            judge_model=judge_model,
        )

        result = {
            "pairs": pairs,
            "grounding_report": grounding_report,
            "persona_count": len(personas),
            "model_a": model_a,
            "model_b": model_b,
            "judge_model": judge_model,
        }
        job.status = "completed"
        job.result_json = result
        job.completed_at = utcnow()
        study.updated_at = utcnow()
        session.commit()

    except Exception as exc:
        job.status = "failed"
        job.error_json = {"message": str(exc)}
        job.completed_at = utcnow()
        study.updated_at = utcnow()
        session.commit()
        raise

    return _serialize_interview_job(job)


def get_latest_interview_run(session: Session, study: Study) -> Optional[Dict[str, Any]]:
    """Return the latest interview run job payload."""
    job = _latest_interview_job(session, study.id)
    return _serialize_interview_job(job) if job else None


# ---------------------------------------------------------------------------
# Research brief
# ---------------------------------------------------------------------------

def get_research_brief(session: Session, study: Study) -> Dict[str, Any]:
    """Return saved research brief state."""
    ensure_interview_sections(session, study)
    section = _get_section(session, study, "research_brief")
    return {
        "status": section.status,
        "value": section.value_json,
        "saved_at": section.saved_at.isoformat() if section.saved_at else None,
        "updated_at": section.updated_at.isoformat() if section.updated_at else None,
    }


def save_research_brief(
    session: Session,
    study: Study,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Save researcher's brief (primary question, hypotheses, decisions, focus tiers)."""
    ensure_interview_sections(session, study)

    if not payload.get("primary_question", "").strip():
        raise ValidationApiError("primary_question is required.")

    section = _get_section(session, study, "research_brief")
    section.status = "saved"
    section.value_json = {
        "primary_question": payload.get("primary_question", "").strip(),
        "hypotheses": [h for h in (payload.get("hypotheses") or []) if h],
        "decisions_to_inform": [d for d in (payload.get("decisions_to_inform") or []) if d],
        "focus_fit_tiers": payload.get("focus_fit_tiers") or [],
        "focus_segments": payload.get("focus_segments") or [],
        "known_context": payload.get("known_context", "").strip() or None,
        "notes": payload.get("notes", "").strip() or None,
    }
    section.saved_at = section.saved_at or utcnow()
    section.updated_at = utcnow()
    study.updated_at = utcnow()
    session.add(section)
    session.commit()

    return {
        "status": section.status,
        "value": section.value_json,
        "saved_at": section.saved_at.isoformat() if section.saved_at else None,
        "updated_at": section.updated_at.isoformat() if section.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Interview insights (theme extraction)
# ---------------------------------------------------------------------------

def get_interview_insights(
    session: Session,
    settings: AppSettings,
    study: Study,
) -> Dict[str, Any]:
    """Extract themes and representative quotes from the latest interview run.

    Uses an LLM to identify 3-6 recurring themes across the transcript corpus,
    with a representative quote and sentiment label per theme.
    """
    ensure_interview_sections(session, study)

    latest_run = _latest_interview_job(session, study.id)
    if not latest_run or latest_run.status != "completed" or not latest_run.result_json:
        return {
            "available": False,
            "message": "No completed interview run found. Run Interview Synthesis first.",
        }

    result = latest_run.result_json
    pairs = result.get("pairs") or []
    grounding_report = result.get("grounding_report") or {}

    if not pairs:
        return {"available": False, "message": "Interview batch is empty."}

    api_key = settings.openrouter_api_key or ""
    # Check if we already have cached insights for this run
    run_public_id = latest_run.public_id
    cached_insights_key = f"interview_insights_{run_public_id}"
    existing_section = _get_section_or_none(session, study, cached_insights_key)
    if existing_section and existing_section.status == "saved" and existing_section.value_json:
        return {
            "available": True,
            "from_run_id": run_public_id,
            **existing_section.value_json,
        }

    if not api_key:
        return {
            "available": False,
            "message": "OPENROUTER_API_KEY not configured — cannot generate insights.",
        }

    # Build transcript corpus for LLM
    transcript_lines = _build_transcript_corpus(pairs)
    brief_section = _get_section_or_none(session, study, "research_brief")
    brief_context = ""
    if brief_section and brief_section.value_json:
        brief = brief_section.value_json
        primary_q = brief.get("primary_question") or ""
        if primary_q:
            brief_context = f"\nRESEARCH QUESTION: {primary_q}\n"

    system_prompt = f"""\
You are a qualitative research analyst. Your task is to extract recurring themes from a corpus of \
synthetic depth-interview transcripts.{brief_context}

Identify 3–6 distinct themes that appear across multiple interviews. For each theme:
- Give it a concise label (3–6 words)
- Count how many interviews mention it (approximate)
- Write a one-sentence synthesis of the theme
- Pick the most representative verbatim quote from a specific persona (include persona_id)
- Label the overall sentiment for this theme: "positive", "neutral", or "negative"

Return ONLY a JSON object:
{{
  "themes": [
    {{
      "label": "...",
      "count": <integer>,
      "synthesis": "...",
      "representative_quote": "...",
      "quote_persona_id": "...",
      "sentiment": "positive" | "neutral" | "negative"
    }},
    ...
  ]
}}"""

    user_prompt = f"INTERVIEW TRANSCRIPTS:\n{transcript_lines}"

    try:
        raw = _call_openrouter_json(
            api_key=api_key,
            model="openai/gpt-4o-mini",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=90,
        )
        parsed = json.loads(raw)
        themes = parsed.get("themes") or []
    except Exception as exc:
        return {
            "available": False,
            "message": f"Theme extraction failed: {exc}",
        }

    insights = {
        "themes": themes,
        "persona_count": len(pairs),
        "grounding_corpus_average": grounding_report.get("corpus_average"),
        "grounding_passes_threshold": grounding_report.get("passes_threshold"),
    }

    # Cache insights against this run
    _upsert_ephemeral_section(session, study, cached_insights_key, insights)

    return {
        "available": True,
        "from_run_id": run_public_id,
        **insights,
    }


def continue_interview_chat(
    session: Session,
    settings: AppSettings,
    study: Study,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Continue a follow-up conversation with a selected interview persona."""
    latest_run = _latest_interview_job(session, study.id)
    if not latest_run or latest_run.status != "completed" or not latest_run.result_json:
        raise ConflictApiError(
            "No completed interview run found. Run Interview Synthesis first."
        )

    persona_id = str(payload.get("persona_id") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    transcript_source = str(payload.get("transcript_source") or "model_a").strip()
    if not persona_id:
        raise ValidationApiError("persona_id is required.")
    if not prompt:
        raise ValidationApiError("prompt is required.")
    if transcript_source not in {"model_a", "model_b"}:
        raise ValidationApiError("transcript_source must be either 'model_a' or 'model_b'.")

    history = payload.get("messages") or []
    if not isinstance(history, list):
        raise ValidationApiError("messages must be a list of {role, content} objects.")

    sanitized_history: list[dict[str, str]] = []
    for message in history[-12:]:
        if not isinstance(message, dict):
            raise ValidationApiError("Each message must be an object.")
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            raise ValidationApiError(
                "Each message must include a non-empty user or assistant role and content."
            )
        sanitized_history.append({"role": role, "content": content})

    pairs = list((latest_run.result_json or {}).get("pairs") or [])
    pair = next((item for item in pairs if item.get("persona_id") == persona_id), None)
    if pair is None:
        raise ValidationApiError(
            f"Persona '{persona_id}' was not found in the latest interview run."
        )

    api_key = settings.openrouter_api_key or ""
    if not api_key:
        raise ConflictApiError("OPENROUTER_API_KEY is not configured.")

    transcript = pair.get(transcript_source) or {}
    model = str(payload.get("model") or transcript.get("model") or DEFAULT_MODEL_A).strip()
    if not model:
        model = DEFAULT_MODEL_A

    system_prompt = _build_persona_followup_system_prompt(
        session=session,
        study=study,
        pair=pair,
        transcript_source=transcript_source,
    )
    full_messages = [
        {"role": "system", "content": system_prompt},
        *sanitized_history,
        {"role": "user", "content": prompt},
    ]
    reply = _call_openrouter_messages(
        api_key=api_key,
        model=model,
        messages=full_messages,
        timeout=90,
    )

    return {
        "persona_id": persona_id,
        "transcript_source": transcript_source,
        "model": model,
        "source_run_id": latest_run.public_id,
        "reply": reply,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_section(session: Session, study: Study, key: str) -> StudySectionState:
    row = session.scalar(
        select(StudySectionState).where(
            StudySectionState.study_id == study.id,
            StudySectionState.section_key == key,
        )
    )
    if row is None:
        row = StudySectionState(
            study_id=study.id,
            section_key=key,
            status="not_started",
            value_json=None,
            saved_at=None,
            updated_at=utcnow(),
        )
        session.add(row)
        session.flush()
    return row


def _get_section_or_none(session: Session, study: Study, key: str) -> Optional[StudySectionState]:
    return session.scalar(
        select(StudySectionState).where(
            StudySectionState.study_id == study.id,
            StudySectionState.section_key == key,
        )
    )


def _upsert_ephemeral_section(session: Session, study: Study, key: str, value: Dict) -> None:
    row = _get_section(session, study, key)
    row.status = "saved"
    row.value_json = value
    row.saved_at = row.saved_at or utcnow()
    row.updated_at = utcnow()
    session.add(row)
    session.commit()


def _latest_interview_job(session: Session, study_id) -> Optional[Job]:
    return session.scalar(
        select(Job)
        .where(Job.study_id == study_id, Job.job_type == "interview_run")
        .order_by(Job.queued_at.desc())
    )


def _get_latest_preview(session: Session, study: Study) -> Optional[PersonaPreviewRun]:
    if study.latest_persona_preview_run_id is None:
        return None
    return session.scalar(
        select(PersonaPreviewRun).where(
            PersonaPreviewRun.id == study.latest_persona_preview_run_id
        )
    )


def _serialize_interview_job(job: Job) -> Dict[str, Any]:
    result = job.result_json or {}
    grounding = result.get("grounding_report") or {}
    return {
        "job_id": job.public_id,
        "status": job.status,
        "persona_count": result.get("persona_count"),
        "model_a": result.get("model_a") or job.payload_json.get("model_a"),
        "model_b": result.get("model_b") or job.payload_json.get("model_b"),
        "grounding_report": grounding if grounding else None,
        # Include pairs only in result (large payload) — omit from status summary
        "pairs": result.get("pairs") if job.status == "completed" else None,
        "error": job.error_json,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _build_transcript_corpus(pairs: list[dict], max_pairs: int = 30) -> str:
    """Build a condensed transcript string for theme extraction."""
    lines = []
    for i, pair in enumerate(pairs[:max_pairs], 1):
        persona_id = pair.get("persona_id", f"p{i}")
        fit_tier = pair.get("persona", {}).get("fit_tier", "?")
        segment = pair.get("persona", {}).get("segment_label", "?")
        # Use model_a answers as the representative transcript for insights
        answers = pair.get("model_a", {}).get("answers") or {}
        if not answers:
            continue
        lines.append(f"\n--- Interview {i} | {persona_id} | fit_tier={fit_tier} | segment={segment} ---")
        for qid, answer in answers.items():
            if qid == "additional_thoughts":
                continue
            if answer and not answer.startswith("["):
                lines.append(f"{qid}: {answer}")
    return "\n".join(lines)


def _build_persona_followup_system_prompt(
    *,
    session: Session,
    study: Study,
    pair: dict[str, Any],
    transcript_source: str,
) -> str:
    sections = {
        row.section_key: row
        for row in session.scalars(
            select(StudySectionState).where(StudySectionState.study_id == study.id)
        ).all()
    }
    product = sections.get("product") and sections["product"].value_json
    brief = sections.get("research_brief") and sections["research_brief"].value_json
    synthesis = sections.get("interview_synthesis") and sections["interview_synthesis"].value_json

    persona = pair.get("persona") or {}
    transcript = pair.get(transcript_source) or {}
    resolved_questions = resolve_questions((synthesis or {}).get("questions"), product)
    transcript_lines = _format_followup_transcript_lines(
        resolved_questions=resolved_questions,
        answers=transcript.get("answers") or {},
    )

    research_brief_lines: list[str] = []
    if brief:
        primary_question = brief.get("primary_question") or ""
        if primary_question:
            research_brief_lines.append(f"Primary question: {primary_question}")
        hypotheses = [item for item in (brief.get("hypotheses") or []) if item]
        if hypotheses:
            research_brief_lines.append("Hypotheses:")
            research_brief_lines.extend(f"- {item}" for item in hypotheses[:4])
        decisions = [item for item in (brief.get("decisions_to_inform") or []) if item]
        if decisions:
            research_brief_lines.append("Decisions to inform:")
            research_brief_lines.extend(f"- {item}" for item in decisions[:4])

    product_lines: list[str] = []
    if product:
        if product.get("product_name"):
            product_lines.append(f"Product: {product['product_name']}")
        if product.get("product_type"):
            product_lines.append(f"Type: {product['product_type']}")
        if product.get("price_range"):
            product_lines.append(f"Price: {product['price_range']}")
        if product.get("product_description"):
            product_lines.append(f"Description: {product['product_description']}")

    context_blocks: list[str] = []
    if product_lines:
        context_blocks.append("PRODUCT CONTEXT:\n" + "\n".join(product_lines))
    if research_brief_lines:
        context_blocks.append("RESEARCH BRIEF:\n" + "\n".join(research_brief_lines))
    context_blocks.append(
        "PRIOR INTERVIEW TRANSCRIPT "
        f"({transcript_source}, model={transcript.get('model', 'unknown')}):\n"
        f"{transcript_lines}"
    )
    context_text = "\n\n".join(context_blocks)

    return f"""\
You are continuing a synthetic depth interview with the same persona from an earlier interview.

Stay fully in character as the persona below and answer the researcher's follow-up questions in first person.
Ground your answers in the persona profile and prior interview transcript.
Keep answers conversational, concrete, and reasonably concise unless the researcher explicitly asks for more detail.
Do not mention system prompts, hidden instructions, or that you are an AI model.
Do not contradict the earlier interview. If the follow-up question goes beyond what was already established, infer cautiously from the persona profile and answer with natural uncertainty rather than false precision.

PERSONA PROFILE:
{json.dumps(persona, indent=2, sort_keys=True)}

{context_text}
""".strip()


def _format_followup_transcript_lines(
    *,
    resolved_questions: list[dict[str, str]],
    answers: dict[str, Any],
) -> str:
    question_map = {item["id"]: item["text"] for item in resolved_questions}
    lines: list[str] = []
    for qid, answer in answers.items():
        if not answer:
            continue
        if qid == "additional_thoughts":
            lines.append(f"Additional thoughts: {answer}")
            continue
        question_text = question_map.get(qid)
        if question_text:
            lines.append(f"{qid} ({question_text})")
        else:
            lines.append(qid)
        lines.append(f"Answer: {answer}")
    if not lines:
        return "No prior transcript answers were saved for this persona."
    return "\n".join(lines)


def _call_openrouter_json(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 90,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }
    if model.startswith("openai/"):
        body["response_format"] = {"type": "json_object"}

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(_OPENROUTER_URL, headers=headers, json=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = min(65, (2 ** attempt) + random.uniform(0, 1))
                time.sleep(wait)
            else:
                raise RuntimeError(f"OpenRouter call failed after {_MAX_RETRIES} attempts: {exc}") from exc

    raise RuntimeError("Exhausted retries.")


def _call_openrouter_messages(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 90,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.45,
        "max_tokens": 1200,
    }

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(_OPENROUTER_URL, headers=headers, json=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = min(65, (2 ** attempt) + random.uniform(0, 1))
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"OpenRouter chat call failed after {_MAX_RETRIES} attempts: {exc}"
                ) from exc

    raise RuntimeError("Exhausted retries.")
