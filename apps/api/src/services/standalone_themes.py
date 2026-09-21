"""Explicit, revision-scoped classroom use of the interview insights service."""
import hashlib
import json
import logging
import re
import unicodedata
from decimal import Decimal

from src.persistence.models import InterviewTurn
from src.services import interview_service as insights
from src.services.exceptions import ConflictApiError, QuotaExceededApiError, TransientProviderError, ValidationApiError
from src.services.llm_budget import (enforce_budget_open, enforce_measured_cost,
    enforce_run_preflight, load_interview_budget_snapshot, lock_class_budget_for_transaction)
from src.services.model_catalog import list_interview_model_catalog
from src.services.standalone_interview import owned_job, serialized_local, usage

MODEL = "openai/gpt-4o-mini"
logger = logging.getLogger(__name__)


def _comparable(text: str) -> str:
    """Fold the ways a model legitimately re-renders a quote it did copy.

    Typographic quotes, the transcript's own "<n>: " answer prefix, wrapping quotation
    marks and run-together whitespace are all rendering, not content. Everything else
    still has to appear in that persona's own answer, so a fabricated or paraphrased
    quote is still rejected.
    """
    folded = unicodedata.normalize("NFKC", text)
    for fancy, plain in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                         ("\u2013", "-"), ("\u2014", "-"), ("\u2026", "...")):
        folded = folded.replace(fancy, plain)
    folded = " ".join(folded.split()).strip().strip('"\'')
    # Either order: a prefix inside the wrapping marks, or marks inside the prefix.
    folded = re.sub(r"^\s*\d+\s*:\s*", "", folded).strip().strip('"\'').strip()
    return folded.casefold()


def validate(themes, pairs):
    """Return why this response is unusable, or None when it is usable."""
    if not isinstance(themes, list):
        return "Response held no theme list"
    if not 3 <= len(themes) <= 6:
        return f"Expected 3-6 themes, got {len(themes)}"
    answers = {p["persona_id"]: list(p["model_a"]["answers"].values()) for p in pairs}
    for index, theme in enumerate(themes, 1):
        if not isinstance(theme, dict):
            return f"Theme {index} is not an object"
        for key in ("label", "synthesis", "representative_quote", "quote_persona_id"):
            if not isinstance(theme.get(key), str) or not theme[key].strip():
                return f"Theme {index} is missing {key}"
        if theme.get("sentiment") not in ("positive", "neutral", "negative"):
            return f"Theme {index} has sentiment {theme.get('sentiment')!r}"
        if type(theme.get("count")) is not int or not 1 <= theme["count"] <= len(pairs):
            return f"Theme {index} count {theme.get('count')!r} is not 1-{len(pairs)}"
        persona_answers = answers.get(theme["quote_persona_id"])
        if persona_answers is None:
            return f"Theme {index} quotes unknown persona {theme['quote_persona_id']!r}"
        quote = _comparable(theme["representative_quote"])
        if not quote or not any(quote in _comparable(answer) for answer in persona_answers):
            return (f"Theme {index} quote is not in {theme['quote_persona_id']}'s answers")
    return None


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
    pairs = insights.rendered_pairs(pairs)
    result = None
    def record_charge(measured):
        # Empty text keeps the accounting row out of the student transcript corpus.
        session.add(InterviewTurn(study_id=study.id, session_id=job_id,
            persona_id="__themes__", role="assistant", text="", model=measured.model,
            tokens_in=measured.tokens_in, tokens_out=measured.tokens_out,
            cost_usd=measured.cost_usd, created_at=insights.utcnow()))
        record.update(outcome="charged", cost_usd=str(measured.cost_usd))

    def call(**prompts):
        nonlocal result
        try:
            result = insights._call_openrouter_messages(api_key=settings.openrouter_api_key, model=MODEL,
                messages=[{"role": "system", "content": prompts["system_prompt"]},
                          {"role": "user", "content": prompts["user_prompt"]}], timeout=90, max_attempts=1)
        except TransientProviderError as exc:
            # The provider charged for this call even though its content is unusable.
            # Record the spend before failing, or the next budget check undercounts
            # it and authorises a call the allowance no longer covers.
            if exc.measured_usage is not None:
                record_charge(exc.measured_usage)
            raise
        record_charge(result)
        try:
            enforce_measured_cost(snapshot, cost_usd=result.cost_usd)
        except QuotaExceededApiError as exc:
            record["budget_stop"] = exc.message
        return result.text

    reason = None
    try:
        themes = insights._extract_insight_themes(pairs, "", call)
        reason = validate(themes, pairs)
        if not reason:
            record["themes"] = themes
    except Exception as exc:
        # Only this module's own validation strings are safe to show the student; a
        # provider exception can carry transcript or credential text.
        reason = exc.__class__.__name__
    if reason:
        # The student pays for every retry, so say which rule the response broke.
        record["reason"] = reason[:200]
        # Key off whether a charge was actually recorded, not whether a usable result
        # came back: a rejected-but-billed response has a known charge and would
        # otherwise be reported to the student as an unknown billing outcome.
        record["message"] = ("Theme extraction failed. Your transcripts are preserved. " +
            ("The response could not be validated; its measured charge is recorded. Retrying adds another charge."
             if record["outcome"] == "charged" else
             "The provider's billing outcome is unknown. Retrying may incur another charge.") +
            f" ({record['reason']})")
    logger.log(logging.INFO if record["themes"] else logging.WARNING, "interview_themes study=%s run=%s revision=%s attempt=%s outcome=%s valid=%s",
        study.public_id, job_id, view["revision"], attempt, record["outcome"], bool(record["themes"]))
    job.result_json = {**job.result_json, "insights": record}
    session.commit()
    return {**status(job), "session_usage": usage(session, settings, job_id)}
