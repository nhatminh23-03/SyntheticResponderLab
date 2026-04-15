from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence.models import Job, PersonaPreviewRun, Study, StudySectionState
from src.services.ids import make_public_id
from src.simulation.interview_prompt_builder import DEFAULT_QUESTIONS, resolve_questions

DEMO_MODEL_A = "openai/gpt-4.1-mini"
DEMO_MODEL_B = "google/gemini-2.5-flash"
DEMO_JUDGE_MODEL = "demo/stamp-fixture"
GROUNDING_THRESHOLD = 0.67
PROTOTYPE_TRANSCRIPTS_PATH = Path("apps/api/demo_data/prototype/interview_transcripts.csv")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_demo_interview_run(
    session: Session,
    study: Study,
    *,
    latest_preview: PersonaPreviewRun,
    product: dict | None,
    questions: list[dict[str, str]] | None = None,
) -> Job:
    existing = session.scalar(
        select(Job)
        .where(Job.study_id == study.id, Job.job_type == "interview_run")
        .order_by(Job.queued_at.desc())
    )
    if existing and existing.status == "completed" and (existing.payload_json or {}).get("demo_fixture"):
        _seed_demo_interview_insights(
            session,
            study,
            job_public_id=existing.public_id,
            result=existing.result_json or {},
        )
        return existing

    result = _build_demo_interview_result(
        latest_preview=latest_preview,
        product=product,
        questions=questions,
    )
    job = Job(
        public_id=make_public_id("job"),
        study_id=study.id,
        job_type="interview_run",
        status="completed",
        payload_json={
            "persona_count": result["persona_count"],
            "model_a": result["model_a"],
            "model_b": result["model_b"],
            "judge_model": result["judge_model"],
            "custom_questions": bool(questions),
            "demo_fixture": True,
        },
        result_json=result,
        error_json=None,
        queued_at=utcnow(),
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(job)
    session.flush()
    _seed_demo_interview_insights(
        session,
        study,
        job_public_id=job.public_id,
        result=result,
    )
    study.updated_at = utcnow()
    session.add(study)
    return job


def _build_demo_interview_result(
    *,
    latest_preview: PersonaPreviewRun,
    product: dict | None,
    questions: list[dict[str, str]] | None,
) -> Dict[str, Any]:
    resolved_questions = resolve_questions(questions or DEFAULT_QUESTIONS, product)
    preview_personas = sorted(latest_preview.personas, key=lambda item: item.row_index)
    prototype_rows = _load_prototype_transcript_rows()

    if prototype_rows:
        pairs = _build_pairs_from_prototype(
            prototype_rows=prototype_rows,
            preview_personas=preview_personas,
            resolved_questions=resolved_questions,
        )
        fixture_source = "prototype_csv"
    else:
        pairs = _build_pairs_from_generated_fixture(
            preview_personas=preview_personas,
            resolved_questions=resolved_questions,
        )
        fixture_source = "generated_fallback"

    return {
        "pairs": pairs,
        "grounding_report": _build_grounding_report(pairs),
        "persona_count": len(pairs),
        "model_a": DEMO_MODEL_A,
        "model_b": DEMO_MODEL_B,
        "judge_model": DEMO_JUDGE_MODEL,
        "demo_fixture": True,
        "fixture_source": fixture_source,
    }


def _build_pairs_from_generated_fixture(
    *,
    preview_personas: list[Any],
    resolved_questions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for index, preview_persona in enumerate(preview_personas):
        persona = preview_persona.persona_json
        profile = _derive_persona_profile(persona)
        pairs.append(
            {
                "persona_id": preview_persona.persona_id,
                "persona_index": index,
                "persona": persona,
                "model_a": {
                    "model": DEMO_MODEL_A,
                    "answers": _build_answers(
                        persona=persona,
                        profile=profile,
                        questions=resolved_questions,
                        variant="a",
                    ),
                    "error": None,
                },
                "model_b": {
                    "model": DEMO_MODEL_B,
                    "answers": _build_answers(
                        persona=persona,
                        profile=profile,
                        questions=resolved_questions,
                        variant="b",
                    ),
                    "error": None,
                },
                "generation_timestamp": utcnow().isoformat(),
            }
        )
    return pairs


def _build_pairs_from_prototype(
    *,
    prototype_rows: list[dict[str, str]],
    preview_personas: list[Any],
    resolved_questions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    question_ids = [question["id"] for question in resolved_questions]
    pairs: list[dict[str, Any]] = []
    for index, (preview_persona, row) in enumerate(zip(preview_personas, prototype_rows)):
        persona = preview_persona.persona_json
        source_answers = _extract_answers_from_row(row, question_ids)
        profile = _derive_persona_profile(persona)
        pairs.append(
            {
                "persona_id": preview_persona.persona_id,
                "persona_index": index,
                "persona": persona,
                "model_a": {
                    "model": _normalize_model_name(row.get("model")),
                    "answers": source_answers,
                    "error": None,
                },
                "model_b": {
                    "model": DEMO_MODEL_B if _normalize_model_name(row.get("model")) == DEMO_MODEL_A else DEMO_MODEL_A,
                    "answers": _build_companion_answers(source_answers, profile),
                    "error": None,
                },
                "generation_timestamp": row.get("generation_timestamp") or utcnow().isoformat(),
            }
        )
    return pairs


def _load_prototype_transcript_rows() -> list[dict[str, str]]:
    root = Path(__file__).resolve().parents[4]
    candidate = root / PROTOTYPE_TRANSCRIPTS_PATH
    if not candidate.exists():
        return []
    raw = candidate.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def _extract_answers_from_row(row: dict[str, str], question_ids: list[str]) -> Dict[str, str]:
    answers: Dict[str, str] = {}
    for question_id in question_ids:
        value = (row.get(question_id) or "").strip()
        if value:
            answers[question_id] = value
    additional_thoughts = (row.get("additional_thoughts") or "").strip()
    if additional_thoughts:
        answers["additional_thoughts"] = additional_thoughts
    return answers


def _normalize_model_name(model_name: Optional[str]) -> str:
    value = (model_name or "").strip().lower()
    return DEMO_MODEL_B if "gemini" in value else DEMO_MODEL_A


def _derive_persona_profile(persona: dict[str, Any]) -> Dict[str, str]:
    fit_tier = str(persona.get("fit_tier") or "soft").lower()
    likely_use_case = str(persona.get("likely_use_case") or "").strip()
    likely_barrier = str(persona.get("likely_barrier") or "").strip()
    segment_label = str(persona.get("segment_label") or "homeowners").strip()

    use_case = likely_use_case or "a flexible backyard room for work, wellness, or overflow space"
    if likely_barrier:
        barrier = likely_barrier
    elif fit_tier == "strong":
        barrier = "permit clarity and confidence that installation will go smoothly"
    elif fit_tier == "soft":
        barrier = "the upfront price and whether the value feels durable"
    elif fit_tier == "latent":
        barrier = "proving I would use it enough to justify the spend"
    else:
        barrier = "whether the footprint fits my yard and priorities"

    intent = {
        "strong": "I can imagine buying something like this soon if the details check out.",
        "soft": "I like the concept, but I still need the economics to feel airtight.",
        "latent": "I am interested, though I am not fully in market without a clearer trigger.",
    }.get(fit_tier, "It is interesting, but I would need a stronger reason to move ahead.")

    return {
        "fit_tier": fit_tier,
        "segment_label": segment_label,
        "use_case": use_case,
        "barrier": barrier,
        "intent": intent,
    }


def _build_answers(
    *,
    persona: dict[str, Any],
    profile: Dict[str, str],
    questions: list[dict[str, str]],
    variant: str,
) -> Dict[str, str]:
    answers: Dict[str, str] = {}
    for question in questions:
        question_id = question["id"]
        use_case = profile["use_case"]
        barrier = profile["barrier"]
        intent = profile["intent"]
        if question_id == "IQ1":
            answers[question_id] = (
                f"I mostly use the house today, which means {use_case} competes with everyday life and never feels fully separate."
            )
        elif question_id == "IQ2":
            answers[question_id] = (
                "The unmet need is dedicated space that feels intentional instead of borrowed from the main house."
            )
        elif question_id == "IQ3":
            answers[question_id] = (
                f"I have looked at alternatives before, but I usually stall once it starts to feel uncertain around {barrier}."
            )
        elif question_id == "IQ4":
            answers[question_id] = (
                f"My ideal version supports {use_case}, has natural light, and still feels flexible enough to change roles later."
            )
        elif question_id == "IQ5":
            answers[question_id] = (
                "It would create cleaner boundaries in my routine and make the main house feel less crowded."
            )
        elif question_id == "IQ6":
            answers[question_id] = (
                f"My first reaction is positive, but I still need proof on quality, comfort, and long-term value. {intent}"
            )
        elif question_id == "IQ7":
            answers[question_id] = (
                f"The main condition is resolving {barrier}. I would move faster with proof from real installs and clear expectations."
            )
        elif question_id == "IQ8":
            answers[question_id] = (
                "I would likely discover it through search, reviews, and people who already own something similar."
            )
        else:
            answers[question_id] = (
                f"I see the appeal for {use_case}. The open issue for me is still {barrier}."
            )

    answers["additional_thoughts"] = (
        f"I keep coming back to the flexibility of the space. The unanswered part is still {profile['barrier']}."
        if variant == "b"
        else f"The concept feels relevant for {profile['use_case']}, and I would want clarity on {profile['barrier']}."
    )
    return answers


def _build_companion_answers(answers: Dict[str, str], profile: Dict[str, str]) -> Dict[str, str]:
    companion: Dict[str, str] = {}
    for question_id, answer in answers.items():
        if question_id == "additional_thoughts":
            companion[question_id] = f"{answer.rstrip()} The open question for me is still {profile['barrier']}."
            continue
        companion[question_id] = f"{answer.rstrip()} That is why I still keep thinking about {profile['barrier']}."
    return companion


def _build_grounding_report(pairs: list[dict[str, Any]]) -> Dict[str, Any]:
    persona_scores = []
    for pair in pairs:
        fit_tier = str(pair.get("persona", {}).get("fit_tier") or "soft").lower()
        if fit_tier == "strong":
            dimensions = {
                "purchase_intent": 1,
                "primary_objection": 1,
                "fit_tier_alignment": 1,
                "use_case_specificity": 1,
            }
        elif fit_tier == "soft":
            dimensions = {
                "purchase_intent": 1,
                "primary_objection": 1,
                "fit_tier_alignment": 1,
                "use_case_specificity": 0,
            }
        elif fit_tier == "latent":
            dimensions = {
                "purchase_intent": 0,
                "primary_objection": 1,
                "fit_tier_alignment": 1,
                "use_case_specificity": 0,
            }
        else:
            dimensions = {
                "purchase_intent": 0,
                "primary_objection": 1,
                "fit_tier_alignment": 0,
                "use_case_specificity": 0,
            }
        score = sum(dimensions.values()) / 4
        persona_scores.append(
            {
                "persona_id": pair["persona_id"],
                "score": round(score, 4),
                "dimension_scores": dimensions,
                "has_error": False,
            }
        )

    if not persona_scores:
        return {
            "corpus_average": 0.0,
            "passes_threshold": False,
            "threshold": GROUNDING_THRESHOLD,
            "per_dimension_avg": {
                "purchase_intent": 0.0,
                "primary_objection": 0.0,
                "fit_tier_alignment": 0.0,
                "use_case_specificity": 0.0,
            },
            "flagged_persona_ids": [],
            "persona_scores": [],
        }

    dimension_names = [
        "purchase_intent",
        "primary_objection",
        "fit_tier_alignment",
        "use_case_specificity",
    ]
    per_dimension_avg = {
        dimension: round(
            sum(score["dimension_scores"][dimension] for score in persona_scores) / len(persona_scores),
            4,
        )
        for dimension in dimension_names
    }
    corpus_average = round(sum(score["score"] for score in persona_scores) / len(persona_scores), 4)
    flagged = [
        score["persona_id"]
        for score in persona_scores
        if score["score"] < GROUNDING_THRESHOLD
    ]
    return {
        "corpus_average": corpus_average,
        "passes_threshold": corpus_average >= GROUNDING_THRESHOLD,
        "threshold": GROUNDING_THRESHOLD,
        "per_dimension_avg": per_dimension_avg,
        "flagged_persona_ids": flagged,
        "persona_scores": persona_scores,
    }


def _seed_demo_interview_insights(
    session: Session,
    study: Study,
    *,
    job_public_id: str,
    result: Dict[str, Any],
) -> None:
    insights = build_demo_interview_insights(job_public_id=job_public_id, result=result)
    key = f"interview_insights_{job_public_id}"
    section = session.scalar(
        select(StudySectionState).where(
            StudySectionState.study_id == study.id,
            StudySectionState.section_key == key,
        )
    )
    if section is None:
        section = StudySectionState(
            study_id=study.id,
            section_key=key,
            status="saved",
            value_json=insights,
            saved_at=utcnow(),
            updated_at=utcnow(),
        )
    else:
        section.status = "saved"
        section.value_json = insights
        section.saved_at = section.saved_at or utcnow()
        section.updated_at = utcnow()
    session.add(section)


def build_demo_interview_insights(
    *,
    job_public_id: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    pairs = list(result.get("pairs") or [])
    grounding = result.get("grounding_report") or {}
    themes = [
        _build_theme(
            label="Dedicated Space Reduces Friction",
            synthesis="Respondents consistently value the product as a way to separate focused work or personal routines from the main house.",
            sentiment="positive",
            pairs=pairs,
            keyword="separate",
            fallback_qid="IQ5",
        ),
        _build_theme(
            label="Value Proof Still Matters",
            synthesis="Interest stays high only when installation quality, comfort, and durability feel strong enough to justify the price.",
            sentiment="negative",
            pairs=pairs,
            keyword="value",
            fallback_qid="IQ6",
        ),
        _build_theme(
            label="Flexibility Expands Appeal",
            synthesis="The room works best when buyers can imagine multiple use cases over time rather than a single fixed role.",
            sentiment="neutral",
            pairs=pairs,
            keyword="flex",
            fallback_qid="IQ4",
        ),
    ]

    return {
        "themes": themes,
        "persona_count": len(pairs),
        "grounding_corpus_average": grounding.get("corpus_average"),
        "grounding_passes_threshold": grounding.get("passes_threshold"),
        "generated_from_demo_fixture": True,
        "from_run_id": job_public_id,
    }


def _build_theme(
    *,
    label: str,
    synthesis: str,
    sentiment: str,
    pairs: list[dict[str, Any]],
    keyword: str,
    fallback_qid: str,
) -> Dict[str, Any]:
    quote = ""
    quote_persona_id = ""
    count = 0
    for pair in pairs:
        answers = pair.get("model_a", {}).get("answers") or {}
        matched = False
        for value in answers.values():
            text = str(value or "")
            if keyword.lower() in text.lower():
                matched = True
                if not quote:
                    quote = text
                    quote_persona_id = pair.get("persona_id", "")
                break
        if matched:
            count += 1

    if not quote and pairs:
        answers = pairs[0].get("model_a", {}).get("answers") or {}
        quote = str(answers.get(fallback_qid) or next(iter(answers.values()), ""))
        quote_persona_id = pairs[0].get("persona_id", "")

    if count == 0:
        count = max(1, len(pairs) // 2)

    return {
        "label": label,
        "count": count,
        "synthesis": synthesis,
        "representative_quote": quote,
        "quote_persona_id": quote_persona_id,
        "sentiment": sentiment,
    }
