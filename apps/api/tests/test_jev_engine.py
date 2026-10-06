from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.adapters.legacy_backend import jev_engine as jev


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

    def unauthorized(request, timeout, context=None):
        import urllib.error, io
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr(jev.urllib.request, "urlopen", unauthorized)
    with pytest.raises(jev.JevRequestError) as error:
        jev.http_transport("secret-key", "https://example.invalid", sleep=lambda s: None)({})
    assert "secret-key" not in error.value.message


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
