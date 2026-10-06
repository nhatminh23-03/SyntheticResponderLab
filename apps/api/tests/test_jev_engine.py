from __future__ import annotations

import json
import math
import threading
import urllib.error
from types import SimpleNamespace

import pytest

from src.adapters.legacy_backend import jev_engine as jev
from src.services.exceptions import ValidationApiError


def Q(id, question_type, options=(), min_value=None, max_value=None):
    return SimpleNamespace(id=id, text=f"text {id}", question_type=question_type, options=list(options),
                           min_value=min_value, max_value=max_value, model_dump=lambda: {})


def test_build_questions_maps_types_and_skips_open_ones():
    questions = [Q("Q1", "likert", ["a", "b", "c", "d", "e"]), Q("Q5_1", "likert", [], 1, 5), Q("Q3", "single_choice", ["Office", "Gym"]),
                 Q("Q20", "multi_choice", ["Ads", "Expo", "Friends"]), Q("Q8", "open_text"), Q("Q9", "numeric")]
    built, skipped = jev.build_questions(questions)
    assert built["Q1"] == {"type": "score", "instructions": "text Q1", "criteria": ["a", "b", "c", "d", "e"]}
    assert built["Q5_1"]["criteria"] == list(jev.GRID_ANCHORS)
    assert built["Q3"] == {"type": "choice", "instructions": "text Q3", "criteria": {"Office": "Office", "Gym": "Gym"}}
    assert built["Q20"]["type"] == "choice"
    assert skipped == ["Q8", "Q9"]


def test_score_keys_are_shifted_and_draws_repeat_with_the_same_key():
    likert = Q("Q1", "likert", ["a", "b", "c", "d", "e"])
    probabilities = jev.probabilities_for({"type": "score", "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.0, "4": 1.0}})
    assert probabilities == {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 1.0}
    assert jev.answer_value(likert, probabilities, "run:P1:Q1") == 5
    spread = jev.probabilities_for({"type": "score", "probabilities": {str(i): 0.2 for i in range(5)}})
    assert jev.answer_value(likert, spread, "run:P1:Q1") == jev.answer_value(likert, spread, "run:P1:Q1")
    multi = Q("Q20", "multi_choice", ["Ads", "Expo", "Friends"])
    picks = jev.answer_value(multi, {"Ads": 0.5, "Expo": 0.3, "Friends": 0.2}, "k")
    assert isinstance(picks, list) and len(picks) == 2 and len(set(picks)) == 2


def test_http_transport_retries_then_raises_and_never_leaks_the_key(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(request, timeout, context=None):
        calls.append(request)
        if len(calls) < 3:
            import urllib.error, io
            raise urllib.error.HTTPError(request.full_url, 429, "busy", {}, io.BytesIO(b"slow down"))
        return Resp(json.dumps({"answers": {}}).encode())

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    send = jev.http_transport("secret-key", "https://example.invalid", sleep=lambda s: None)
    assert send({"model": "jev-latest"}) == {"answers": {}}
    assert len(calls) == 3

    # Test that a 401 with key in body redacts the key and doesn't retry
    calls.clear()
    def unauthorized(request, timeout, context=None):
        calls.append(request)
        import urllib.error, io
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"bad key secret-key here"))

    monkeypatch.setattr(jev.urllib.request, "urlopen", unauthorized)
    with pytest.raises(jev.JevRequestError) as error:
        jev.http_transport("secret-key", "https://example.invalid", sleep=lambda s: None)({})
    assert "secret-key" not in error.value.message
    assert "***" in error.value.message
    assert len(calls) == 1

    # Test that retryable 503 exhausts retries without leaking key
    calls.clear()
    def unavailable(request, timeout, context=None):
        calls.append(request)
        import urllib.error, io
        raise urllib.error.HTTPError(request.full_url, 503, "service", {}, io.BytesIO(b"secret-key"))

    monkeypatch.setattr(jev.urllib.request, "urlopen", unavailable)
    with pytest.raises(RuntimeError) as error:
        jev.http_transport("secret-key", "https://example.invalid", retries=4, sleep=lambda s: None)({})
    assert "secret-key" not in str(error.value)
    assert len(calls) == 4

    # Test redaction happens before truncation: 195 'x' chars + key should not show key prefix
    calls.clear()
    def long_body_with_key(request, timeout, context=None):
        calls.append(request)
        import urllib.error, io
        body = b"x" * 195 + b"secret-key"
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(body))

    monkeypatch.setattr(jev.urllib.request, "urlopen", long_body_with_key)
    with pytest.raises(jev.JevRequestError) as error:
        jev.http_transport("secret-key", "https://example.invalid", sleep=lambda s: None)({})
    # Verify key was redacted before truncation (no key prefix appears)
    assert "secret-key" not in error.value.message
    assert "secr" not in error.value.message  # No prefix of the key
    assert "***" in error.value.message

    # Test unreadable error body on retryable 503 is retried (4 times), not escaped after 1 attempt
    calls.clear()
    class BadHTTPError(urllib.error.HTTPError):
        def read(self):
            raise IOError("cannot read")

    def unreadable_503(request, timeout, context=None):
        calls.append(request)
        raise BadHTTPError(request.full_url, 503, "service", {}, None)

    monkeypatch.setattr(jev.urllib.request, "urlopen", unreadable_503)
    with pytest.raises(RuntimeError):
        jev.http_transport("secret-key", "https://example.invalid", retries=4, sleep=lambda s: None)({})
    # Verify it retried all 4 times (not escaped after 1 attempt)
    assert len(calls) == 4


def _stub_runtime(n_personas=2):
    schemas = SimpleNamespace(MockResponseRecord=lambda **kw: SimpleNamespace(**kw))
    config = SimpleNamespace(run_id="RUN_X", experiment_mode="split", survey_title="T", sample_size=n_personas,
                             selected_models=[jev.JEV_MODEL_ID])
    def persona(i, age):
        return SimpleNamespace(persona_id=f"P{i}", segment_label=None,
                               model_dump=lambda **kw: {"persona_id": f"P{i}", "age_bucket": age, "fit_tier": "strong"})
    personas = [persona(i, "45-54" if i == n_personas else "30-34") for i in range(1, n_personas + 1)]
    survey = SimpleNamespace(questions=[Q("Q1", "likert", ["a", "b", "c", "d", "e"]), Q("Q8", "open_text")], description=None)
    return schemas, config, personas, survey


def _transport_failing_on(age, sent):
    def transport(payload):
        sent.append(payload)
        if payload["state"]["respondent"].get("age_bucket") == age:
            raise RuntimeError("timeout")
        return {"answers": {"Q1": {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1, "4": 0}}}}
    return transport


def test_failed_respondents_and_unsupported_questions_are_missing_never_invented():
    schemas, config, personas, survey = _stub_runtime(n_personas=5)   # the last persona fails: 1 of 5 = 20%, allowed
    sent = []
    records, debug, is_fallback, probabilities = jev.generate_jev_records(
        schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
        business_product_context=None, market_context=None, transport=_transport_failing_on("45-54", sent), max_concurrency=2)
    assert [(r.respondent_id, r.question_id, r.answer) for r in records] == [(f"RESP_00{i}", "Q1", 4) for i in range(1, 5)]
    assert is_fallback == [False] * 4                       # nothing filled in: no Q8 rows, no rows for RESP_005
    assert debug["respondents_completed"] == 4 and debug["respondents_failed"] == 1
    assert "4 of 5 live respondents completed; 1 failed." in debug["jev_warnings"]
    assert any("Q8" in w for w in debug["jev_warnings"])
    assert all("fit_tier" not in p["state"]["respondent"] and "persona_id" not in p["state"]["respondent"] for p in sent)
    assert probabilities["RESP_001"]["Q1"]["4"] == 1 and "RESP_005" not in probabilities


def test_more_than_a_fifth_failing_fails_the_run_visibly():
    schemas, config, personas, survey = _stub_runtime(n_personas=2)   # 1 of 2 = 50% failed
    with pytest.raises(jev.JevTooManyFailuresError) as error:
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None,
                                 transport=_transport_failing_on("45-54", []), max_concurrency=2)
    assert "1 of 2" in error.value.message and "retry" in error.value.message.lower()


def test_all_respondents_failing_raises_unavailable():
    schemas, config, personas, survey = _stub_runtime()

    def transport(payload):
        raise RuntimeError("down")

    with pytest.raises(jev.JevUnavailableError):
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None, transport=transport, max_concurrency=2)


def test_all_zero_and_nan_probabilities_stay_missing():
    """Unusable probabilities (all-zero, NaN, etc.) count as missing questions, not failed respondents."""
    schemas, config, personas, survey = _stub_runtime(n_personas=2)
    def transport(payload):
        # All responses have Q1 but with different unusable probabilities
        if payload["state"]["respondent"].get("age_bucket") == "30-34":
            # All-zero probabilities
            return {"answers": {"Q1": {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}}}}
        else:
            # NaN probabilities
            return {"answers": {"Q1": {"type": "score", "probabilities": {"0": float('nan'), "1": 0, "2": 0, "3": 0, "4": 0}}}}

    # Both respondents return valid structure but no usable answers → both fail
    with pytest.raises(jev.JevUnavailableError):
        jev.generate_jev_records(
            schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
            business_product_context=None, market_context=None, transport=transport, max_concurrency=2)


def test_empty_answers_dict_fails_respondent():
    """A respondent returning empty answers dict is treated as failed."""
    schemas, config, personas, survey = _stub_runtime(n_personas=2)
    def transport(payload):
        return {"answers": {}}  # No answers for any question

    with pytest.raises(jev.JevUnavailableError):
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None, transport=transport, max_concurrency=2)


def test_invalid_reply_structure_fails_respondent():
    """A respondent returning invalid reply structure (e.g. non-dict) is treated as failed."""
    schemas, config, personas, survey = _stub_runtime(n_personas=2)
    call_count = [0]
    def transport(payload):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"error": "something went wrong"}  # Missing "answers" key
        return {"answers": {"Q1": {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1, "4": 0}}}}

    with pytest.raises(jev.JevTooManyFailuresError) as error:
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None, transport=transport, max_concurrency=2)
    assert "1 of 2" in error.value.message


def test_non_numeric_probability_key_stays_missing():
    """A non-numeric probability key for a score question is caught and the question stays missing."""
    schemas, config, personas, survey = _stub_runtime(n_personas=2)
    def transport(payload):
        # Return Q1 with a non-numeric key
        return {"answers": {"Q1": {"type": "score", "probabilities": {"not_a_number": 0.5, "0": 0.5}}}}

    # Both respondents have non-numeric keys → both fail
    with pytest.raises(jev.JevUnavailableError):
        jev.generate_jev_records(
            schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
            business_product_context=None, market_context=None, transport=transport, max_concurrency=2)


def test_jev_request_error_propagates():
    """A JevRequestError from the transport is not caught and propagates out."""
    schemas, config, personas, survey = _stub_runtime()
    def transport(payload):
        raise jev.JevRequestError("bad API key")

    with pytest.raises(jev.JevRequestError):
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None, transport=transport, max_concurrency=2)


def test_no_askable_questions_raises_validation_error():
    """If the survey has no askable questions, raise ValidationApiError before calling transport."""
    schemas, config, personas, survey = _stub_runtime()
    survey.questions = [Q("Q8", "open_text"), Q("Q9", "numeric")]  # Only unsupported types

    with pytest.raises(ValidationApiError) as error:
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None, transport=lambda x: {}, max_concurrency=2)
    assert "Jev answers only questions with listed options" in error.value.message


def test_multi_choice_one_hot_yields_exactly_one():
    """A one-hot multi-choice reply (only one option has weight) draws exactly that one."""
    schemas, config, personas, survey = _stub_runtime(n_personas=2)
    survey.questions = [Q("Q20", "multi_choice", ["Ads", "Expo", "Friends"])]

    def transport(payload):
        # Return one-hot for Q20 (Ads=1.0, Expo=0, Friends=0)
        return {"answers": {"Q20": {"type": "choice", "probabilities": {"Ads": 1.0, "Expo": 0, "Friends": 0}}}}

    records, debug, is_fallback, probabilities = jev.generate_jev_records(
        schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
        business_product_context=None, market_context=None, transport=transport, max_concurrency=2)

    # Both respondents should have exactly ['Ads'] as the answer (not ['Ads', 'Friends'] or similar)
    for record in records:
        assert record.answer == ["Ads"], f"Expected ['Ads'], got {record.answer}"


def test_mixed_usable_and_unusable_questions_in_one_respondent():
    """A respondent with one usable and one unusable question keeps the usable answer, other is missing."""
    schemas, config, personas, survey = _stub_runtime(n_personas=2)
    survey.questions = [Q("Q1", "likert", ["a", "b", "c", "d", "e"]), Q("Q2", "single_choice", ["X", "Y"])]

    def transport(payload):
        # Return Q1 with usable probabilities, Q2 with all-zero (unusable)
        return {"answers": {
            "Q1": {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1, "4": 0}},
            "Q2": {"type": "choice", "probabilities": {"X": 0, "Y": 0}}
        }}

    records, debug, is_fallback, probabilities = jev.generate_jev_records(
        schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
        business_product_context=None, market_context=None, transport=transport, max_concurrency=2)

    # Should have exactly 2 records (both respondents × 1 usable question)
    assert len(records) == 2
    assert all(r.question_id == "Q1" for r in records)
    assert debug["respondents_completed"] == 2
    assert debug["respondents_failed"] == 0
    assert debug["questions_missing"] == 2  # Both Q2s are missing (all-zero)


# --- Final fix: blank answers reported, answers checked against what we asked, global cap, gentler retries, run deadline ---

LIKERT = ["a", "b", "c", "d", "e"]
USABLE_SCORE = {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1, "4": 0}}   # draws 4
ZERO_SCORE = {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}}


def _numbered_runtime(n_personas, questions):
    """Personas told apart by a prompted field (persona_id is never sent to Jev)."""
    schemas = SimpleNamespace(MockResponseRecord=lambda **kw: SimpleNamespace(**kw))
    config = SimpleNamespace(run_id="RUN_X", experiment_mode="split", survey_title="T", sample_size=n_personas,
                             selected_models=[jev.JEV_MODEL_ID])

    def persona(i):
        return SimpleNamespace(persona_id=f"P{i}", segment_label=None,
                               model_dump=lambda **kw: {"persona_id": f"P{i}", "income_band": f"band-{i}"})

    personas = [persona(i) for i in range(1, n_personas + 1)]
    survey = SimpleNamespace(questions=list(questions), description=None)
    return schemas, config, personas, survey


def _band(payload):
    return int(payload["state"]["respondent"]["income_band"].split("-")[1])


def _run(n_personas, questions, transport, **kwargs):
    schemas, config, personas, survey = _numbered_runtime(n_personas, questions)
    return jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                    business_product_context=None, market_context=None, transport=transport,
                                    max_concurrency=kwargs.pop("max_concurrency", 2), **kwargs)


def test_blank_answers_are_reported_per_question_in_survey_order_over_completed_respondents():
    questions = [Q("SQ1", "likert", LIKERT), Q("Q1", "likert", LIKERT), Q("Q7", "single_choice", ["X", "Y"])]

    def transport(payload):
        band = _band(payload)
        if band == 5:
            raise RuntimeError("timeout")                            # failed respondent: not counted in "of 4"
        return {"answers": {
            "SQ1": USABLE_SCORE if band == 4 else ZERO_SCORE,       # blank for respondents 1-3
            "Q1": USABLE_SCORE,
            "Q7": {"type": "choice", "probabilities": {"X": 0, "Y": 0} if band == 1 else {"X": 1.0}},
        }}

    records, debug, _fallback, _probabilities = _run(5, questions, transport)
    assert ("Jev gave no usable answer for some questions, so they are left blank: SQ1 (3 of 4 respondents), Q7 (1 of 4)."
            in debug["jev_warnings"])
    assert "4 of 5 live respondents completed; 1 failed." in debug["jev_warnings"]
    assert sorted((r.respondent_id, r.question_id) for r in records if r.question_id != "Q1") == [
        ("RESP_002", "Q7"), ("RESP_003", "Q7"), ("RESP_004", "Q7"), ("RESP_004", "SQ1")]
    assert debug["questions_missing"] == 4


def test_no_blank_answer_warning_when_every_answer_is_usable():
    _records, debug, _fallback, _probabilities = _run(3, [Q("Q1", "likert", LIKERT)], lambda payload: {"answers": {"Q1": USABLE_SCORE}})
    assert not any("no usable answer" in warning for warning in debug["jev_warnings"])


def test_score_keys_outside_one_to_five_after_the_shift_are_dropped():
    asked = {"type": "score", "instructions": "x", "criteria": LIKERT}
    assert jev.probabilities_for({"type": "score", "probabilities": {"-1": 0.5, "0": 0.1, "4": 0.2, "5": 0.7}}, asked) == {"1": 0.1, "5": 0.2}
    # Nearly all of Jev's weight sits on a point we never offered: the answer comes only from the offered points.
    reply = {"answers": {"Q1": {"type": "score", "probabilities": {"4": 0.0001, "7": 0.9999}}}}
    records, _debug, _fallback, probabilities = _run(3, [Q("Q1", "likert", LIKERT)], lambda payload: reply)
    assert [r.answer for r in records] == [5, 5, 5]
    assert probabilities["RESP_001"]["Q1"] == {"5": 0.0001}


def test_a_score_answer_with_only_out_of_range_keys_is_blank_and_counted():
    questions = [Q("Q1", "likert", LIKERT), Q("Q2", "likert", LIKERT)]
    reply = {"answers": {"Q1": USABLE_SCORE, "Q2": {"type": "score", "probabilities": {"5": 0.6, "9": 0.4}}}}
    records, debug, _fallback, _probabilities = _run(2, questions, lambda payload: reply)
    assert {r.question_id for r in records} == {"Q1"}
    assert "Jev gave no usable answer for some questions, so they are left blank: Q2 (2 of 2 respondents)." in debug["jev_warnings"]


def test_choice_keys_that_are_not_among_the_options_are_dropped():
    asked = {"type": "choice", "instructions": "x", "criteria": {"Office": "Office", "Gym": "Gym"}}
    assert jev.probabilities_for({"type": "choice", "probabilities": {"Office": 0.2, "Garage": 0.8}}, asked) == {"Office": 0.2}
    questions = [Q("Q3", "single_choice", ["Office", "Gym"]), Q("Q20", "multi_choice", ["Ads", "Expo", "Friends"])]
    reply = {"answers": {"Q3": {"type": "choice", "probabilities": {"Office": 0.0001, "Garage": 0.9999}},
                         "Q20": {"type": "choice", "probabilities": {"Ads": 0.1, "Radio": 0.8, "Expo": 0.1}}}}
    records, _debug, _fallback, _probabilities = _run(4, questions, lambda payload: reply)
    assert all(r.answer == "Office" for r in records if r.question_id == "Q3")
    assert all(set(r.answer) <= {"Ads", "Expo"} for r in records if r.question_id == "Q20")


def test_the_score_shift_follows_the_question_we_asked_not_the_type_jev_echoes():
    # Jev echoes "choice" for a 1-5 question: still shifted from 0-based anchors.
    reply = {"answers": {"Q1": {"type": "choice", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1, "4": 0}}}}
    records, _debug, _fallback, _probabilities = _run(2, [Q("Q1", "likert", LIKERT)], lambda payload: reply)
    assert [r.answer for r in records] == [4, 4]
    # Jev echoes "score" for a choice question whose options are digits: never shifted.
    reply = {"answers": {"Q4": {"type": "score", "probabilities": {"1": 0, "2": 1.0, "3": 0}}}}
    records, _debug, _fallback, _probabilities = _run(2, [Q("Q4", "single_choice", ["1", "2", "3"])], lambda payload: reply)
    assert [r.answer for r in records] == ["2", "2"]


class _Resp:
    def __init__(self, body): self.body = body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _http_error(code, headers=None, body=b"busy"):
    import io
    return urllib.error.HTTPError("https://example.invalid", code, "x", headers or {}, io.BytesIO(body))


def test_backoff_is_exponential_capped_at_eight_seconds_with_up_to_one_second_of_jitter(monkeypatch):
    delays, jitters = [], []
    monkeypatch.setattr(jev.urllib.request, "urlopen", lambda request, timeout, context=None: (_ for _ in ()).throw(_http_error(500)))
    for _ in range(20):
        delays.clear()
        with pytest.raises(RuntimeError):
            jev.http_transport("k", "https://example.invalid", retries=6, sleep=delays.append)({})
        assert len(delays) == 5
        for attempt, delay in enumerate(delays):
            base = min(2 ** attempt, 8)          # 1, 2, 4, 8, 8
            assert base <= delay <= base + 1
            jitters.append(delay - base)
    assert len({round(j, 6) for j in jitters}) > 1   # jittered, so threads do not retry in lockstep


@pytest.mark.parametrize("code, retry_after, expected", [
    (429, "3", 3.0), (503, "2.5", 2.5), (429, "120", 10.0), (503, "600", 10.0)])
def test_retry_after_on_429_and_503_is_honoured_and_capped_at_ten_seconds(monkeypatch, code, retry_after, expected):
    delays, calls = [], []

    def urlopen(request, timeout, context=None):
        calls.append(request)
        if len(calls) == 1:
            raise _http_error(code, {"Retry-After": retry_after})
        return _Resp(b'{"answers": {}}')

    monkeypatch.setattr(jev.urllib.request, "urlopen", urlopen)
    assert jev.http_transport("k", "https://example.invalid", sleep=delays.append)({}) == {"answers": {}}
    assert delays == [expected]


@pytest.mark.parametrize("code, headers", [(429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), (500, {"Retry-After": "5"}),
                                           (429, {"Retry-After": "-4"}), (503, {})])
def test_retry_after_that_is_not_numeric_or_not_on_429_503_falls_back_to_backoff(monkeypatch, code, headers):
    delays, calls = [], []

    def urlopen(request, timeout, context=None):
        calls.append(request)
        if len(calls) == 1:
            raise _http_error(code, headers)
        return _Resp(b'{"answers": {}}')

    monkeypatch.setattr(jev.urllib.request, "urlopen", urlopen)
    jev.http_transport("k", "https://example.invalid", sleep=delays.append)({})
    assert len(delays) == 1 and 1 <= delays[0] <= 2


def test_one_process_wide_semaphore_caps_jev_requests_at_sixteen():
    assert jev.JEV_GLOBAL_MAX_CONCURRENCY == 16
    slots = jev._JEV_SLOTS
    assert isinstance(slots, type(threading.BoundedSemaphore(1)))
    taken = 0
    try:
        while slots.acquire(blocking=False):
            taken += 1
        assert taken == 16
    finally:
        for _ in range(taken):
            slots.release()


def test_the_semaphore_is_held_around_each_attempt_and_released_before_the_backoff_sleep(monkeypatch):
    log = []

    class Slots:
        def acquire(self, blocking=True, timeout=None):
            log.append("acquire")
            return True

        def release(self):
            log.append("release")

    def urlopen(request, timeout, context=None):
        log.append("urlopen")
        if log.count("urlopen") == 1:
            raise _http_error(429)
        return _Resp(b'{"answers": {}}')

    monkeypatch.setattr(jev, "_JEV_SLOTS", Slots())
    monkeypatch.setattr(jev.urllib.request, "urlopen", urlopen)
    jev.http_transport("k", "https://example.invalid", sleep=lambda s: log.append("sleep"))({})
    assert log == ["acquire", "urlopen", "release", "sleep", "acquire", "urlopen", "release"]


class FakeClock:
    def __init__(self, now=1000.0): self.now = now
    def __call__(self): return self.now


def test_transport_caps_each_call_timeout_at_the_time_left_before_the_deadline(monkeypatch):
    clock, timeouts = FakeClock(), []

    def urlopen(request, timeout, context=None):
        timeouts.append(timeout)
        return _Resp(b'{"answers": {}}')

    monkeypatch.setattr(jev.urllib.request, "urlopen", urlopen)
    jev.http_transport("k", "https://example.invalid", timeout=30, deadline=clock.now + 12, clock=clock)({})
    jev.http_transport("k", "https://example.invalid", timeout=30, deadline=clock.now + 100, clock=clock)({})
    assert timeouts == [12, 30]


def test_transport_never_starts_an_attempt_or_a_backoff_sleep_past_the_deadline(monkeypatch):
    clock, calls, delays = FakeClock(), [], []
    monkeypatch.setattr(jev.urllib.request, "urlopen", lambda request, timeout, context=None: calls.append(timeout))
    with pytest.raises(jev.JevDeadlineExceeded) as error:
        jev.http_transport("k", "https://example.invalid", deadline=clock.now, clock=clock, sleep=delays.append)({})
    assert str(error.value) == "Jev did not answer before the run deadline"
    assert calls == [] and delays == []

    def busy(request, timeout, context=None):
        calls.append(timeout)
        raise _http_error(429, {"Retry-After": "8"})

    monkeypatch.setattr(jev.urllib.request, "urlopen", busy)
    with pytest.raises(jev.JevDeadlineExceeded):   # an 8 s wait would end past a deadline 5 s away: no sleep, no retry
        jev.http_transport("k", "https://example.invalid", deadline=clock.now + 5, clock=clock, sleep=delays.append)({})
    assert calls == [5] and delays == []


def test_transport_waits_for_a_free_slot_only_until_the_deadline(monkeypatch):
    clock, waits, calls = FakeClock(), [], []

    class FullSlots:
        def acquire(self, blocking=True, timeout=None):
            waits.append(timeout)
            return False

        def release(self):
            raise AssertionError("nothing was acquired")

    monkeypatch.setattr(jev, "_JEV_SLOTS", FullSlots())
    monkeypatch.setattr(jev.urllib.request, "urlopen", lambda *a, **k: calls.append(1))
    with pytest.raises(jev.JevDeadlineExceeded):
        jev.http_transport("k", "https://example.invalid", deadline=clock.now + 7, clock=clock, sleep=lambda s: None)({})
    assert waits == [7] and calls == []


def test_run_deadline_and_call_timeout_constants():
    assert jev.JEV_RUN_DEADLINE_SECONDS == 150
    assert jev.JEV_CALL_TIMEOUT_SECONDS == 30


def test_respondents_not_answered_by_the_run_deadline_fail_and_all_failing_gives_unavailable():
    clock, sent = FakeClock(), []

    def slow(payload):          # blocks past the deadline, then "answers": too late to count
        sent.append(payload)
        clock.now += jev.JEV_RUN_DEADLINE_SECONDS + 1
        return {"answers": {"Q1": USABLE_SCORE}}

    with pytest.raises(jev.JevUnavailableError) as error:
        _run(4, [Q("Q1", "likert", LIKERT)], slow, max_concurrency=1, clock=clock)
    assert "Jev did not answer before the run deadline" in error.value.message
    assert len(sent) == 1        # nobody else is asked once the deadline has passed


def test_one_respondent_past_the_deadline_out_of_five_is_reported_and_the_rest_are_kept():
    clock = FakeClock()

    def transport(payload):
        if _band(payload) == 5:
            clock.now += jev.JEV_RUN_DEADLINE_SECONDS     # the last respondent hangs until the deadline
            raise jev.JevDeadlineExceeded()
        clock.now += 1
        return {"answers": {"Q1": USABLE_SCORE}}

    records, debug, _fallback, _probabilities = _run(5, [Q("Q1", "likert", LIKERT)], transport, max_concurrency=1, clock=clock)
    assert [r.respondent_id for r in records] == ["RESP_001", "RESP_002", "RESP_003", "RESP_004"]
    assert "4 of 5 live respondents completed; 1 failed." in debug["jev_warnings"]


def test_more_than_a_fifth_past_the_deadline_fails_the_run_visibly():
    clock = FakeClock()

    def transport(payload):
        clock.now += 50          # 1st, 2nd, 3rd answer in time (t=50, 100, 150); the 4th and 5th are never started
        return {"answers": {"Q1": USABLE_SCORE}}

    with pytest.raises(jev.JevTooManyFailuresError) as error:
        _run(5, [Q("Q1", "likert", LIKERT)], transport, max_concurrency=1, clock=clock)
    assert "3 of 5" in error.value.message


def test_an_explicit_deadline_is_used_as_given():
    clock = FakeClock()
    with pytest.raises(jev.JevUnavailableError) as error:
        _run(2, [Q("Q1", "likert", LIKERT)], lambda payload: {"answers": {"Q1": USABLE_SCORE}}, clock=clock, deadline=clock.now - 1)
    assert "run deadline" in error.value.message
