"""Live survey answers from TypeSafe's Jev classifier, one answer drawn per question from its probabilities.

Ported from research/neo_persona_set/phase3/jev_survey.py. Jev answers each question in isolation and
returns a probability per option; we draw one answer at those odds, seeded per run, respondent and
question, so a rerun repeats and the panel keeps Jev's spread instead of its single safest guess.
"""
from __future__ import annotations

import json
import math
import random
import ssl
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.services.exceptions import ProviderUnavailableApiError, ValidationApiError

JEV_MODEL_ID = "typesafe/jev"
JEV_API_MODEL = "jev-latest"
GRID_ANCHORS = ("Would not reduce my likelihood at all", "Would reduce my likelihood slightly",
                "Would reduce my likelihood moderately", "Would reduce my likelihood a lot", "Would strongly reduce my likelihood")
GENERIC_ANCHORS = ("1 - lowest", "2", "3", "4", "5 - highest")
PERSONA_EXCLUDED = {"persona_id", "fit_tier", "awareness_stage"}   # fit_tier is scored after, never prompted (SPEC P0.2)
RETRYABLE = {408, 429}
RETRY_AFTER_CODES = {429, 503}              # a numeric Retry-After on these replaces the backoff (capped)
RETRY_AFTER_CAP_SECONDS = 10
BACKOFF_CAP_SECONDS = 8
SCORE_POINTS = 5

# Ruling R16: a live Jev run ends (answers, demo fallback or a visible 503) well before the web proxy's 300 s cut.
JEV_RUN_DEADLINE_SECONDS = 150
JEV_CALL_TIMEOUT_SECONDS = 30
DEADLINE_MESSAGE = "Jev did not answer before the run deadline"

# One cap on Jev requests in flight for the whole process, shared by every run: a class of ~30 students may
# press Run live together, and each run has its own respondent pool.
JEV_GLOBAL_MAX_CONCURRENCY = 16
_JEV_SLOTS = threading.BoundedSemaphore(JEV_GLOBAL_MAX_CONCURRENCY)

try:
    import certifi
    _SSL: Optional[ssl.SSLContext] = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL = None


class JevUnavailableError(ProviderUnavailableApiError):
    """Jev answered no respondent (network, timeouts, 5xx): the run falls back to the preloaded demo."""


class JevRequestError(ProviderUnavailableApiError):
    """Jev refused the request (bad key, bad payload): the run stops with this message."""


class JevTooManyFailuresError(ProviderUnavailableApiError):
    """More than MAX_FAILED_SHARE of respondents failed: the run fails visibly so the instructor can retry."""


class JevDeadlineExceeded(RuntimeError):
    """The run deadline came before Jev answered this respondent; the respondent is failed, never filled in."""

    def __init__(self) -> None:
        super().__init__(DEADLINE_MESSAGE)


MAX_FAILED_SHARE = 0.20


Transport = Callable[[Dict[str, Any]], Dict[str, Any]]


def _retry_after_seconds(error: urllib.error.HTTPError) -> Optional[float]:
    """A numeric Retry-After on a 429/503, capped; None when absent, not a number, or on another status."""
    if error.code not in RETRY_AFTER_CODES:
        return None
    try:
        raw = error.headers.get("Retry-After") if error.headers is not None else None
        value = float(str(raw).strip()) if raw is not None else None
    except (AttributeError, TypeError, ValueError):
        return None
    if value is None or math.isnan(value) or math.isinf(value) or value < 0:
        return None
    return min(value, RETRY_AFTER_CAP_SECONDS)


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with jitter, so many threads hit by the same 429 do not retry in lockstep."""
    return min(2 ** attempt, BACKOFF_CAP_SECONDS) + random.uniform(0, 1)


def http_transport(api_key: str, url: str, *, timeout: float = JEV_CALL_TIMEOUT_SECONDS, retries: int = 4,
                   sleep: Callable[[float], None] = time.sleep, deadline: Optional[float] = None,
                   clock: Callable[[], float] = time.monotonic) -> Transport:
    """POST one respondent to Jev. With a (monotonic) deadline, no attempt, slot wait or backoff sleep runs past it."""

    def remaining() -> Optional[float]:
        return None if deadline is None else deadline - clock()

    def send(payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode()
        last: Optional[Exception] = None
        for attempt in range(retries):
            left = remaining()
            if left is not None and left <= 0:
                raise JevDeadlineExceeded()
            slots = _JEV_SLOTS
            if not (slots.acquire() if left is None else slots.acquire(timeout=left)):
                raise JevDeadlineExceeded()
            wait_hint: Optional[float] = None
            try:
                left = remaining()
                if left is not None and left <= 0:
                    raise JevDeadlineExceeded()
                call_timeout = timeout if left is None else min(timeout, left)
                request = urllib.request.Request(url, data=body, method="POST",
                                                 headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(request, timeout=call_timeout, context=_SSL) as response:
                        return json.loads(response.read().decode())
                except urllib.error.HTTPError as error:
                    try:
                        raw_body = error.read().decode(errors="replace")
                    except Exception:
                        raw_body = ""
                    # Redact key before truncating to preserve the fact that it was present
                    detail = raw_body.replace(api_key, "***")[:200]
                    if error.code not in RETRYABLE and error.code < 500:
                        raise JevRequestError(f"Jev refused the request (HTTP {error.code}): {detail}") from None
                    last = RuntimeError(f"HTTP {error.code}")
                    wait_hint = _retry_after_seconds(error)
                except Exception as error:  # noqa: BLE001 - retried below
                    last = error
            finally:
                slots.release()
            if attempt < retries - 1:
                delay = wait_hint if wait_hint is not None else _backoff_seconds(attempt)
                left = remaining()
                if left is not None and delay >= left:
                    raise JevDeadlineExceeded()
                sleep(delay)
        raise RuntimeError(f"Jev request failed after {retries} attempts: {last}")
    return send


def build_questions(questions: List[Any]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    built: Dict[str, Dict[str, Any]] = {}
    skipped: List[str] = []
    for question in questions:
        text = " ".join(str(question.text or "").split())
        options = list(question.options or [])
        if question.question_type == "likert":
            if len(options) != 5:
                options = list(GRID_ANCHORS if str(question.id).upper().startswith("Q5_") else GENERIC_ANCHORS)
            built[question.id] = {"type": "score", "instructions": text, "criteria": options}
        elif question.question_type in {"single_choice", "multi_choice"} and options:
            built[question.id] = {"type": "choice", "instructions": text, "criteria": {o: o for o in options}}
        else:
            skipped.append(question.id)
    return built, skipped


def probabilities_for(answer: Dict[str, Any], asked: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Jev's stated odds, keyed like the question we asked (``asked``, from build_questions).

    The score shift follows the type we built, not the type Jev echoes. A score key must map to 1..5 after the
    shift and a choice key must be one of the question's options; any other key is dropped. A score key that is
    not a whole number at all means the reply is not in the format we asked for: it raises, so the answer stays
    missing.
    """
    raw = answer.get("probabilities") or {}
    kind = (asked or {}).get("type") or answer.get("type")
    if kind == "score":
        shifted: Dict[str, float] = {}
        for key, value in raw.items():
            point = int(key) + 1                         # Jev counts score anchors from 0
            if 1 <= point <= SCORE_POINTS:
                shifted[str(point)] = float(value)
        return shifted
    options = set((asked or {}).get("criteria") or ()) if asked else None
    return {str(k): float(v) for k, v in raw.items() if options is None or str(k) in options}


def usable_probabilities(stated: Dict[str, float]) -> Optional[Dict[str, float]]:
    """Return the dict if all values are finite positive numbers and total > 0, else None."""
    if not stated:
        return None
    for value in stated.values():
        try:
            if not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    total = sum(max(v, 0.0) for v in stated.values())
    return stated if total > 0 else None


def _draw(probabilities: Dict[str, float], rng: random.Random) -> str:
    """Draw one option from usable probabilities (assume caller validated with usable_probabilities)."""
    total = sum(max(v, 0.0) for v in probabilities.values())
    if total <= 0:
        raise ValueError("Cannot draw from non-positive total probabilities")
    point, cumulative = rng.random() * total, 0.0
    for option, share in probabilities.items():
        cumulative += max(share, 0.0)
        if point < cumulative:
            return option
    return list(probabilities)[-1]


def answer_value(question: Any, probabilities: Dict[str, float], key: str) -> Any:
    rng = random.Random(key)
    if question.question_type == "likert":
        return int(_draw(probabilities, rng))
    if question.question_type == "multi_choice":
        # Cap k at the number of options with positive weight (at least 1)
        positive_weight_count = sum(1 for v in probabilities.values() if v > 0)
        k = max(1, min(int(getattr(question, "max_value", None) or 2), positive_weight_count))
        remaining, picks = dict(probabilities), []
        for _ in range(k):
            choice = _draw(remaining, rng)
            picks.append(choice)
            remaining.pop(choice, None)
        return picks
    return _draw(probabilities, rng)


def _respondent(persona: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field, value in persona.model_dump(exclude_none=True).items():
        if field in PERSONA_EXCLUDED or value in ("", [], None):
            continue
        out[field] = "; ".join(value) if isinstance(value, list) else value
    return out


def _stimulus(product: Any, market: Any, description: Optional[str]) -> str:
    parts = []
    for block in (product, market):
        if block is not None:
            dumped = {k: v for k, v in block.model_dump(exclude_none=True).items() if v not in ("", [], None)}
            parts.append(json.dumps(dumped, ensure_ascii=False))
    if description:
        parts.append(description)
    return "\n\n".join(parts)


def generate_jev_records(*, schemas: Any, config: Any, survey_schema: Any, persona_profiles: List[Any],
                         business_product_context: Any, market_context: Any, transport: Transport,
                         max_concurrency: int, deadline: Optional[float] = None,
                         clock: Callable[[], float] = time.monotonic,
                         ) -> Tuple[List[Any], Dict[str, Any], List[bool], Dict[str, Dict[str, Dict[str, float]]]]:
    """A Jev answer is kept; a Jev failure is missing. Nothing is ever filled in.

    ``deadline`` is a ``clock()`` (monotonic) time; by default the run gets JEV_RUN_DEADLINE_SECONDS from now. A
    respondent not answered by then is failed, and the usual failure gates apply to the counts.
    """
    run_deadline = deadline if deadline is not None else clock() + JEV_RUN_DEADLINE_SECONDS
    questions = list(survey_schema.questions)
    jev_questions, skipped = build_questions(questions)
    if not jev_questions:
        raise ValidationApiError("Jev answers only questions with listed options (1–5 scale or choices); this survey has none.")
    stimulus = _stimulus(business_product_context, market_context, getattr(survey_schema, "description", None))
    respondents = [(f"RESP_{i:03d}", persona_profiles[(i - 1) % len(persona_profiles)]) for i in range(1, config.sample_size + 1)]

    def ask(item: Tuple[str, Any]) -> Tuple[Optional[Dict[str, Dict[str, float]]], Optional[str]]:
        """Parse and validate the reply. Return (usable_answers, error) where usable_answers is a dict of question_id -> probabilities."""
        _rid, persona = item
        if clock() >= run_deadline:
            return None, DEADLINE_MESSAGE                # never started: the run is out of time
        payload = {"model": JEV_API_MODEL, "state": {"respondent": _respondent(persona), "stimulus": stimulus}, "questions": jev_questions}
        try:
            reply = transport(payload)
        except JevRequestError:
            raise
        except JevDeadlineExceeded:
            return None, DEADLINE_MESSAGE
        except Exception as error:  # noqa: BLE001 - one respondent failing is recorded, not fatal
            if clock() >= run_deadline:
                return None, DEADLINE_MESSAGE
            return None, f"{type(error).__name__}: {error}"
        if clock() > run_deadline:
            return None, DEADLINE_MESSAGE                # answered too late to count

        # Validate reply structure and parse probabilities
        try:
            if not isinstance(reply, dict):
                return None, f"Jev returned non-dict reply: {type(reply)}"
            answers = reply.get("answers")
            if not isinstance(answers, dict):
                return None, f"Jev returned non-dict answers: {type(answers)}"
        except Exception as error:
            return None, f"Failed to parse reply: {error}"

        usable_answers: Dict[str, Dict[str, float]] = {}
        for question_id in jev_questions:
            try:
                stated = probabilities_for(answers.get(question_id) or {}, jev_questions[question_id])
                if usable_probabilities(stated):
                    usable_answers[question_id] = stated
            except (ValueError, TypeError, AttributeError):
                pass  # skip this question for this respondent

        if not usable_answers:
            return None, "Jev returned no usable answers"
        return usable_answers, None

    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, len(respondents)))) as pool:
        replies = list(pool.map(ask, respondents))
    failed = sum(1 for reply, _ in replies if reply is None)
    total = len(respondents)
    if replies and failed == total:
        raise JevUnavailableError(f"Jev did not answer any respondent: {replies[0][1]}")
    if failed / total > MAX_FAILED_SHARE:
        raise JevTooManyFailuresError(f"Jev answered only {total - failed} of {total} respondents ({failed} failed). "
                                      "Nothing was filled in; please retry the run.")

    records: List[Any] = []
    probabilities_out: Dict[str, Dict[str, Dict[str, float]]] = {}
    missing_answers = 0
    missing_by_question: Dict[str, int] = {}
    for (respondent_id, persona), (usable_answers, _error) in zip(respondents, replies):
        if usable_answers is None:
            continue                                   # a failed respondent stays missing
        for question in questions:
            if question.id not in jev_questions:
                continue                               # unsupported question type
            stated = usable_answers.get(question.id)
            if stated is None:
                missing_answers += 1                   # an unanswered or unusable question stays missing
                missing_by_question[question.id] = missing_by_question.get(question.id, 0) + 1
                continue
            value = answer_value(question, stated, f"{config.run_id}:{respondent_id}:{question.id}")
            probabilities_out.setdefault(respondent_id, {})[question.id] = stated
            records.append(schemas.MockResponseRecord(respondent_id=respondent_id, model=JEV_MODEL_ID, experiment_mode=config.experiment_mode,
                                                      survey_title=config.survey_title, question_id=question.id, question_text=question.text,
                                                      question_type=question.question_type, answer=value,
                                                      segment_label=getattr(persona, "segment_label", None), run_id=config.run_id))
    completed = total - failed
    warnings = [f"{completed} of {total} live respondents completed; {failed} failed."] if failed else []
    if skipped:
        warnings.append(f"Jev answers only questions with listed options; these have no answers: {', '.join(skipped)}")
    blank_ids: List[str] = []
    for question in questions:                         # survey order
        if missing_by_question.get(question.id) and question.id not in blank_ids:
            blank_ids.append(question.id)
    if blank_ids:
        counts = [f"{qid} ({missing_by_question[qid]} of {completed}{' respondents' if index == 0 else ''})"
                  for index, qid in enumerate(blank_ids)]
        warnings.append(f"Jev gave no usable answer for some questions, so they are left blank: {', '.join(counts)}.")
    debug = {"generation_mode": "jev_live", "model": JEV_MODEL_ID, "executions": completed, "answer_records": len(records),
             "questions_total": len(records), "request_errors": failed, "provider_error_count": 0, "malformed_json_count": 0,
             "questions_fallback_to_mock": 0, "questions_parsed_from_live": len(records), "questions_missing": missing_answers,
             "respondents_completed": completed, "respondents_failed": failed, "jev_warnings": warnings}
    return records, debug, [False] * len(records), probabilities_out
