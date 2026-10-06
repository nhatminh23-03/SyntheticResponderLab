"""Explicit, revision-scoped classroom use of the interview insights service."""
import hashlib
import json
import logging
import re
import time
import unicodedata
from decimal import Decimal

from src.persistence.models import InterviewTurn
from src.services import interview_service as insights
from src.services.exceptions import ConflictApiError, QuotaExceededApiError, TransientProviderError, ValidationApiError
from src.services.llm_budget import (enforce_budget_open, enforce_measured_cost,
    enforce_run_preflight, load_interview_budget_snapshot, lock_class_budget_for_transaction)
from src.services.interview_scoring import POST_INTERVIEW_SCORE_LABEL, classify_interview_transcript
from src.services.model_catalog import list_interview_model_catalog
from src.services.standalone_interview import owned_job, serialized_local, usage

MODEL = "openai/gpt-4o-mini"
# One extraction plus at most one guided re-ask. Every estimate, consent figure and
# preflight is sized for this many calls, because that is what one authorization buys.
MAX_PROVIDER_CALLS = 2
# PA3.5's memo shape, the same floors the focus group's memo uses.
MEMO_MIN_ANSWER_OPTIONS = 3
# A survey option is short by design, so the "in a participant's own words" check is
# near-vacuous without a floor: a single letter is a substring of almost any answer.
# Three words is the shortest thing that reads as an option ("too far away").
MEMO_MIN_OPTION_WORDS = 3
# The completion ceiling for one extraction. The quoted price and the call itself both
# read it, so a student can never confirm a ceiling the call is allowed to exceed.
MEMO_MAX_COMPLETION_TOKENS = 4000
# One authorization's whole provider budget, shared across those calls. The class
# budget lock is held for the entire request, so two serial 90s calls would double
# how long every other student waits behind it.
PROVIDER_DEADLINE_S = 90
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


def _grounded(text, persona_id, answers):
    """Did this persona actually say this? Verbatim, once the rendering is folded away."""
    persona_answers = answers.get(persona_id)
    if persona_answers is None:
        return False
    folded = _comparable(text)
    return bool(folded) and any(folded in _comparable(answer) for answer in persona_answers)


def validate(memo, pairs):
    """Return why this response is unusable, or None when it is usable.

    The memo is themes + exactly one surprise + at least three closed-ended answer
    options, which is what PA3.5 asks a student to hand in. Every quote and every
    option has to be the participant's own words, or the memo is evidence of nothing.
    """
    if not isinstance(memo, dict):
        return "Response was not a memo object"
    themes = memo.get("themes")
    if not isinstance(themes, list):
        return "Response held no theme list"
    if not 3 <= len(themes) <= 6:
        return f"Expected 3-6 themes, got {len(themes)}"
    answers = {}
    for pair in pairs:
        answers.setdefault(pair["persona_id"], []).extend(pair["model_a"]["answers"].values())
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
        if theme["quote_persona_id"] not in answers:
            return f"Theme {index} quotes unknown persona {theme['quote_persona_id']!r}"
        if not _grounded(theme["representative_quote"], theme["quote_persona_id"], answers):
            return (f"Theme {index} quote is not in {theme['quote_persona_id']}'s answers")

    surprise = memo.get("surprise")
    if not isinstance(surprise, dict):
        return "Memo is missing its surprise"
    for key in ("summary", "quote", "quote_persona_id"):
        if not isinstance(surprise.get(key), str) or not surprise[key].strip():
            return f"Surprise is missing {key}"
    if surprise["quote_persona_id"] not in answers:
        return f"Surprise quotes unknown persona {surprise['quote_persona_id']!r}"
    if not _grounded(surprise["quote"], surprise["quote_persona_id"], answers):
        return f"Surprise quote is not in {surprise['quote_persona_id']}'s answers"

    options = memo.get("answer_options")
    if not isinstance(options, list) or len(options) < MEMO_MIN_ANSWER_OPTIONS:
        return (f"Expected at least {MEMO_MIN_ANSWER_OPTIONS} answer options, got "
                f"{len(options) if isinstance(options, list) else 0}")
    seen = set()
    for index, option in enumerate(options, 1):
        if not isinstance(option, dict):
            return f"Answer option {index} is not an object"
        for key in ("text", "quote_persona_id"):
            if not isinstance(option.get(key), str) or not option[key].strip():
                return f"Answer option {index} is missing {key}"
        if option["quote_persona_id"] not in answers:
            return f"Answer option {index} quotes unknown persona {option['quote_persona_id']!r}"
        if not _grounded(option["text"], option["quote_persona_id"], answers):
            return (f"Answer option {index} is not in {option['quote_persona_id']}'s answers")
        folded = _comparable(option["text"])
        if len(folded.split()) < MEMO_MIN_OPTION_WORDS:
            return (f"Answer option {index} is shorter than {MEMO_MIN_OPTION_WORDS} words, "
                    f"which is not a survey option")
        if folded in seen:
            return f"Answer option {index} repeats an earlier option"
        seen.add(folded)
    return None


def corpus(job):
    transcripts = (job.result_json or {}).get("transcripts", [])
    revision = hashlib.sha256(json.dumps(transcripts, sort_keys=True).encode()).hexdigest()
    pairs = [{"persona_id": t["persona_id"], "model_a": {"answers": {
        str(i): m["content"] for i, m in enumerate(t["messages"]) if m["role"] == "assistant"
    }}} for t in transcripts]
    return revision, pairs


SENTIMENTS = ("positive", "neutral", "negative")


def _answers(transcript):
    """The interviewee's own turns — the unit the classifier was built for.

    The classifier filters role == "assistant" itself (interview_scoring.py:114-119) and
    raises on a turn holding no answer, so an interviewer question was already skipped.
    Doing it here too puts the rule where the next reader sees it: the interviewer's
    phrasing reaching a distribution labelled "the room" is the bug below in another form.
    """
    return [turn for turn in (transcript.get("messages") or [])
            if isinstance(turn, dict)
            and str(turn.get("role") or "").strip() == "assistant"
            and str(turn.get("content") or turn.get("text") or "").strip()]


def _answer_labels(answers):
    """Classify each answer on its own, because that is the unit the classifier was built for.

    Run over a whole transcript it is systematically wrong here. Its negative vocabulary
    is concern language — worried, concerned, nervous, skeptical — which accumulates with
    every question a depth interview asks, while its positive vocabulary is eight literal
    feeling words an articulate interviewee may never use. "A separate quiet studio signals
    that I'm serious about my business" scores zero positive; "I worry about it becoming an
    oven" scores negative. So a keen buyer reads negative the longer you talk to them.
    """
    for turn in answers:
        try:
            label = classify_interview_transcript([turn])["emotional_classification"]
        except Exception:
            continue
        if label in SENTIMENTS:
            yield label


def emotion(job):
    """The batch's emotional read, per ANSWER — never a verdict on a person.

    Lexical and deterministic, so it costs nothing and is still there when a paid theme
    extraction is rejected. It reports how answers distribute, not what an interviewee
    "is": this lexicon is far better at noticing voiced concern than voiced enthusiasm,
    and a per-person label built on it mislabels the enthusiastic.
    """
    personas = []
    transcripts = (job.result_json or {}).get("transcripts", [])
    counts = {name: 0 for name in SENTIMENTS}
    for transcript in transcripts:
        answers = _answers(transcript)
        labels = list(_answer_labels(answers))
        if not labels:
            # An interviewee who never answered has no language to classify; leaving them
            # out is honest, counting them as neutral is not.
            continue
        try:
            fit_tier = classify_interview_transcript(transcript["messages"])["fit_tier"]
        except Exception:
            # A persona whose fit was never established does not belong in a count called
            # "scored" — and its answers must not reach the distribution either, or the
            # header would describe a room the numbers were not drawn from.
            continue
        for label in labels:
            counts[label] += 1
        personas.append({"persona_id": transcript.get("persona_id"), "fit_tier": fit_tier,
            # Answers GIVEN and answers the classifier could read are two numbers. Folding
            # them into one is the same silent shrinkage `interviewed` exists to prevent.
            "answers": len(answers), "classified": len(labels),
            **{name: sum(label == name for label in labels) for name in SENTIMENTS}})
    # Carry the batch's own size: a skipped interviewee otherwise silently shrinks the
    # room, and the student reads a distribution as if it covered everyone.
    return {"personas": personas, "counts": counts, "scored": len(personas),
            "answers": sum(counts.values()), "interviewed": len(transcripts),
            "label": POST_INTERVIEW_SCORE_LABEL}


def status(job):
    revision, pairs = corpus(job)
    saved = (job.result_json or {}).get("insights")
    # Eligibility reads the batch as RUN, not as rendered: a single placeholder answer
    # must not silently take the whole batch out of eligibility, which is how a student
    # would experience the button simply doing nothing. A corpus the renderer cannot use
    # is refused loudly at extraction time instead.
    complete = (job.status == "completed" and bool(pairs) and
        len(pairs) == job.payload_json.get("persona_count") and
        all(len(p["model_a"]["answers"]) >= job.payload_json.get("turn_limit", 8) for p in pairs))
    # Conservative planning estimate: at most one token per UTF-8 byte plus the
    # provider's output-token cap, at this model's catalog rates, times the most
    # calls one authorization can make. Estimated over the corpus actually sent, which
    # is the narrowed one. The student confirms the ceiling, never a best case.
    prompt = (insights._insights_system_prompt()
              + insights._build_transcript_corpus(insights.rendered_pairs(pairs)))
    model = next(m for m in list_interview_model_catalog()["models"] if m["id"] == MODEL)
    estimate = MAX_PROVIDER_CALLS * (
        (Decimal(len(prompt.encode()) + 100) * Decimal(str(model["prompt_price_per_million"])) +
         Decimal(MEMO_MAX_COMPLETION_TOKENS) *
         Decimal(str(model["completion_price_per_million"]))) / Decimal(1000000))
    return {"from_run_id": job.public_id, "revision": revision, "eligible": complete,
        "available": bool(saved and saved.get("themes")), "stale": bool(saved and saved["revision"] != revision),
        "message": "Generate themes to compare with your hand-coding." if complete else
            f"Themes require a completed, nonempty batch. This run is {job.status}; its transcripts remain available.",
        "estimated_cost_usd": str(estimate), "model": MODEL, "saved": saved,
        "emotion": emotion(job)}


@serialized_local
def standalone_themes(session, settings, study, job_id, payload=None):
    job = owned_job(session, study, job_id, "standalone_batch", lock=True)
    if (job.payload_json or {}).get("demo"):
        from src.services.demo_mode import refuse_demo, ZERO_USAGE
        if payload is not None:
            refuse_demo(job)
        saved = (job.result_json or {}).get("insights")
        return {"from_run_id": job_id, "revision": job.result_json["revision"], "eligible": False,
                "available": bool(saved), "stale": False, "saved": saved, "session_usage": dict(ZERO_USAGE),
                "message": "Saved fixture themes." if saved else "No themes were saved in this demo. Demo (no AI): read-only",
                "estimated_cost_usd": "0", "model": "pre-recorded"}
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
    if not pairs:
        # An empty corpus can only come back rejected, and the student pays either way.
        raise ConflictApiError("These transcripts hold no answers to extract themes from.")
    result = None
    spent = Decimal(0)
    deadline = time.monotonic() + PROVIDER_DEADLINE_S
    def record_charge(measured):
        # Empty text keeps the accounting row out of the student transcript corpus.
        session.add(InterviewTurn(study_id=study.id, session_id=job_id,
            persona_id="__themes__", role="assistant", text="", model=measured.model,
            tokens_in=measured.tokens_in, tokens_out=measured.tokens_out,
            cost_usd=measured.cost_usd, created_at=insights.utcnow()))
        # Accumulate: a guided re-ask is a second billed call, and the student is
        # told a charge was recorded, so that number has to be every call's.
        record.update(outcome="charged",
            cost_usd=str(Decimal(record.get("cost_usd", "0")) + measured.cost_usd))

    def call(**prompts):
        nonlocal result
        try:
            result = insights._call_openrouter_messages(api_key=settings.openrouter_api_key, model=MODEL,
                messages=[{"role": "system", "content": prompts["system_prompt"]},
                          {"role": "user", "content": prompts["user_prompt"]}],
                timeout=max(10, int(deadline - time.monotonic())), max_attempts=1,
                # A persona answer is a paragraph; this response is 3-6 themes with
                # verbatim quotes plus a surprise plus 3+ grounded options. At the
                # shared default it can stop mid-object, and an unusable response is
                # billed, is not a rule the re-ask can fix, and saves nothing.
                max_tokens=MEMO_MAX_COMPLETION_TOKENS)
        except TransientProviderError as exc:
            # The provider charged for this call even though its content is unusable.
            # Record the spend before failing, or the next budget check undercounts
            # it and authorises a call the allowance no longer covers.
            if exc.measured_usage is not None:
                record_charge(exc.measured_usage)
            else:
                record["unknown_billing"] = True
            raise
        except Exception:
            # One authorization can make two calls. An earlier call that billed
            # cleanly must not let a later one that vanished be reported as a known,
            # recorded charge — the student would be told the ledger is complete.
            record["unknown_billing"] = True
            raise
        record_charge(result)
        nonlocal spent
        spent += result.cost_usd
        try:
            # The snapshot is frozen at its pre-call reading, so a per-call check would
            # let two calls that each fit the remaining allowance exceed it together.
            enforce_measured_cost(snapshot, cost_usd=spent)
        except QuotaExceededApiError as exc:
            record["budget_stop"] = exc.message
        return result.text

    def extract(correction=""):
        def guided(**prompts):
            if correction:
                prompts["user_prompt"] += (
                    f"\n\nYour previous response was rejected: {correction}\n"
                    "Return the whole JSON object again with that fixed. Every quoted "
                    "string \u2014 each representative_quote, the surprise quote, and every "
                    "answer_options text \u2014 must be copied character for character from "
                    "an answer by the persona you name in its quote_persona_id.")
            return call(**prompts)
        return insights._extract_insight_themes(pairs, "", guided)

    reason, validated = None, False
    try:
        memo = extract()
        validated = True
        reason = validate(memo, pairs)
        if reason and not record.get("budget_stop"):
            # ponytail: one guided re-ask. A rejected response is usually a formatting
            # slip the student cannot see or fix, and making them pay to press Retry
            # for it is the failure they actually experience. One extra call, then the
            # reason is theirs. Raise this only if the second call is also missing.
            record["retried_reason"] = reason[:200]
            # Feed back the truncated reason: it is built from model-controlled fields,
            # and an oversized one would inflate the second prompt without limit.
            # A second call that never parses did not break a rule, so say so.
            validated = False
            memo = extract(record["retried_reason"])
            validated = True
            reason = validate(memo, pairs)
        if not reason:
            record["themes"] = memo["themes"]
            # The surprise and the options are the rest of what PA3.5 grades; a page
            # that only shows themes hands the student two thirds of a memo.
            record["surprise"] = memo["surprise"]
            record["answer_options"] = memo["answer_options"]
    except Exception as exc:
        # A provider exception can carry transcript or credential text, so only its class
        # is shown. Validation reasons are ours, and quote only the response's own field.
        reason = exc.__class__.__name__
    if reason:
        # The student pays for every retry, so say which rule the response broke.
        record["reason"] = reason[:200]
        # Key off whether a charge was actually recorded, not whether a usable result
        # came back: a rejected-but-billed response has a known charge and would
        # otherwise be reported to the student as an unknown billing outcome.
        # Two different failures reach here: a response that broke a rule, and a call
        # that never produced one. Saying which is the point of showing a reason at all.
        record["message"] = ("Theme extraction failed. Your transcripts are preserved. " +
            ("The response broke a rule; " if validated else "The call produced no usable response; ") +
            ("its measured charge is recorded. Retrying adds another charge."
             if record["outcome"] == "charged" and not record.get("unknown_billing") else
             "the provider's billing outcome is unknown. Retrying may incur another charge.") +
            f" ({record['reason']})")
    logger.log(logging.INFO if record["themes"] else logging.WARNING, "interview_themes study=%s run=%s revision=%s attempt=%s outcome=%s valid=%s",
        study.public_id, job_id, view["revision"], attempt, record["outcome"], bool(record["themes"]))
    job.result_json = {**job.result_json, "insights": record}
    session.commit()
    return {**status(job), "session_usage": usage(session, settings, job_id)}
