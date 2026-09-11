"""Explicit, revision-scoped classroom use of the interview insights service."""
import hashlib
import json
import logging
from decimal import Decimal

from src.persistence.models import InterviewTurn
from src.services import interview_service as insights
from src.services.exceptions import ConflictApiError, QuotaExceededApiError, ValidationApiError
from src.services.llm_budget import (enforce_budget_open, enforce_measured_cost,
    enforce_run_preflight, load_interview_budget_snapshot, lock_class_budget_for_transaction)
from src.services.model_catalog import list_interview_model_catalog
from src.services.standalone_interview import owned_job, serialized_local, usage

MODEL = "openai/gpt-4o-mini"
logger = logging.getLogger(__name__)


def corpus(job):
    transcripts = (job.result_json or {}).get("transcripts", [])
    revision = hashlib.sha256(json.dumps(transcripts, sort_keys=True).encode()).hexdigest()
    pairs = [{"persona_id": t["persona_id"], "model_a": {"answers": {
        str(i): m["content"] for i, m in enumerate(t["messages"]) if m["role"] == "assistant"
    }}} for t in transcripts]
    return revision, pairs


def status(job):
    revision, pairs = corpus(job)
    saved = (job.result_json or {}).get("insights")
    complete = (job.status == "completed" and bool(pairs) and
        len(pairs) == job.payload_json.get("persona_count") and
        all(len(p["model_a"]["answers"]) >= job.payload_json.get("turn_limit", 8) for p in pairs))
    # Conservative planning estimate: at most one token per UTF-8 byte plus the
    # provider's 2,000 output-token cap, at this model's catalog rates.
    prompt = insights._insights_system_prompt() + insights._build_transcript_corpus(pairs)
    model = next(m for m in list_interview_model_catalog()["models"] if m["id"] == MODEL)
    estimate = (Decimal(len(prompt.encode()) + 100) * Decimal(str(model["prompt_price_per_million"])) +
                Decimal(2000) * Decimal(str(model["completion_price_per_million"]))) / Decimal(1000000)
    return {"from_run_id": job.public_id, "revision": revision, "eligible": complete,
        "available": bool(saved and saved.get("themes")), "stale": bool(saved and saved["revision"] != revision),
        "message": "Generate themes to compare with your hand-coding." if complete else
            f"Themes require a completed, nonempty batch. This run is {job.status}; its transcripts remain available.",
        "estimated_cost_usd": str(estimate), "model": MODEL, "saved": saved}


@serialized_local
def standalone_themes(session, settings, study, job_id, payload=None):
    job = owned_job(session, study, job_id, "standalone_batch", lock=True)
    view = {**status(job), "session_usage": usage(session, settings, job_id)}
    if payload is None:
        return view
    if not view["eligible"]:
        return view
    if payload.get("revision") != view["revision"]:
        raise ConflictApiError("Transcripts changed. Review the new extraction estimate before confirming.")
    saved = view["saved"]
    if saved and not view["stale"]:
        if saved.get("themes"):
            return view
        # Versioned attempts prevent queued retries from charging twice.
        if payload.get("retry_attempt") != saved.get("attempt"):
            return view
    if payload.get("authorize_charge") is not True:
        raise ValidationApiError("Confirm the additional theme-extraction charge first.")
    if settings.cache_mode == "replay_only":
        raise ConflictApiError("Cache-only mode: no saved themes exist for these transcripts.")
    lock_class_budget_for_transaction(session)
    snapshot = load_interview_budget_snapshot(session, session_id=job_id, run_budget_usd=settings.llm_budget_usd)
    enforce_budget_open(snapshot)
    enforce_run_preflight(estimated_cost_usd=Decimal(view["estimated_cost_usd"]) + snapshot.run_spent_usd,
        class_spent_usd=snapshot.class_spent_usd - snapshot.run_spent_usd, run_budget_usd=snapshot.run_budget_usd)
    if not settings.openrouter_api_key:
        raise ConflictApiError("Theme extraction is not configured.")
    attempt = (saved.get("attempt", 0) if saved else 0) + 1
    record = {"revision": view["revision"], "attempt": attempt, "outcome": "unknown", "themes": None}
    _, pairs = corpus(job)
    result = None
    def call(**prompts):
        nonlocal result
        result = insights._call_openrouter_messages(api_key=settings.openrouter_api_key, model=MODEL,
            messages=[{"role": "system", "content": prompts["system_prompt"]},
                      {"role": "user", "content": prompts["user_prompt"]}], timeout=90, max_attempts=1)
        # Empty text keeps the accounting row out of the student transcript corpus.
        session.add(InterviewTurn(study_id=study.id, session_id=job_id,
            persona_id="__themes__", role="assistant", text="", model=result.model,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out, cost_usd=result.cost_usd,
            created_at=insights.utcnow()))
        record.update(outcome="charged", cost_usd=str(result.cost_usd))
        try:
            enforce_measured_cost(snapshot, cost_usd=result.cost_usd)
        except QuotaExceededApiError as exc:
            record["budget_stop"] = exc.message
        return result.text

    try:
        themes = insights._extract_insight_themes(pairs, "", call)
        if not isinstance(themes, list) or not 3 <= len(themes) <= 6:
            raise ValueError("Expected 3–6 themes")
        answers = {p["persona_id"]: list(p["model_a"]["answers"].values()) for p in pairs}
        for theme in themes:
            if (not isinstance(theme, dict) or
                any(not isinstance(theme.get(k), str) or not theme[k].strip() for k in
                    ("label", "synthesis", "representative_quote", "quote_persona_id")) or
                theme.get("sentiment") not in ("positive", "neutral", "negative") or
                type(theme.get("count")) is not int or not 1 <= theme["count"] <= len(pairs) or
                not any(theme["representative_quote"] in answer for answer in answers.get(theme["quote_persona_id"], []))):
                raise ValueError("Invalid or ungrounded theme")
        record["themes"] = themes
    except Exception:
        record["message"] = ("Theme extraction failed. Your transcripts are preserved. " +
            ("The provider's billing outcome is unknown. Retrying may incur another charge." if result is None else
             "The response could not be validated; its measured charge is recorded. Retrying adds another charge."))
    logger.log(logging.INFO if record["themes"] else logging.WARNING, "interview_themes study=%s run=%s revision=%s attempt=%s outcome=%s valid=%s",
        study.public_id, job_id, view["revision"], attempt, record["outcome"], bool(record["themes"]))
    job.result_json = {**job.result_json, "insights": record}
    session.commit()
    return {**status(job), "session_usage": usage(session, settings, job_id)}
