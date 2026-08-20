"""Provider requests run concurrently without changing run output.

Respondent requests used to be issued one at a time, so a 20-respondent run
serialized 20 provider round-trips. They are now dispatched through a thread
pool; these tests pin the two properties that must survive that change:
results stay in respondent order, and the calls genuinely overlap.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adapters.legacy_backend import domain
from src.adapters.legacy_backend.runtime import load_module


API_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = API_ROOT / "legacy_runtime"


@pytest.fixture(scope="module")
def legacy():
    return SimpleNamespace(
        schemas=load_module("backend.schemas", LEGACY_ROOT),
        run_manager=load_module("backend.simulation.run_manager", LEGACY_ROOT),
        prompt_builder=load_module("backend.simulation.prompt_builder", LEGACY_ROOT),
    )


def _survey(legacy, question_count: int = 3):
    return legacy.schemas.SurveySchema(
        survey_title="Concurrency Fixture Survey",
        questions=[
            legacy.schemas.SurveyQuestion(
                id=f"Q{index}",
                text=f"Question {index}?",
                question_type="likert",
                min_value=1,
                max_value=5,
            )
            for index in range(1, question_count + 1)
        ],
    )


def _run(legacy, llm_client, *, sample_size: int, max_concurrency: int):
    persona_generator = load_module("backend.simulation.persona_generator", LEGACY_ROOT)
    audience = legacy.schemas.AudienceFilter()
    # Seeded so persona sampling is identical across runs; otherwise grounded
    # sampling redraws and the comparison below would test the wrong thing.
    personas = persona_generator.generate_persona_profiles(
        audience_filter=audience, sample_size=sample_size, seed=42
    )
    config = legacy.schemas.SimulationRunConfig(
        run_id="RUN_CONCURRENCY",
        survey_title="Concurrency Fixture Survey",
        survey_question_count=3,
        sample_size=sample_size,
        selected_models=["model-a", "model-b"],
        experiment_mode="split",
        reruns_per_persona=1,
    )
    return domain._generate_live_response_records_with_debug(
        schemas=legacy.schemas,
        run_manager=legacy.run_manager,
        llm_client=llm_client,
        prompt_builder=legacy.prompt_builder,
        config=config,
        survey_schema=_survey(legacy),
        audience_filter=audience,
        persona_profiles=personas,
        business_product_context=legacy.schemas.BusinessProductContext(
            product_name="Concurrency Fixture Product",
            product_description="A fixture product used to exercise the live run path.",
        ),
        market_context=legacy.schemas.MarketContext(),
        prompt_user_template_override=None,
        max_concurrency=max_concurrency,
    )


class _RecordingClient:
    """Stub provider that answers every question and tracks call overlap."""

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self._lock = threading.Lock()
        self._active = 0
        self.peak_concurrency = 0
        self.calls = 0

    def generate_survey_response_with_openrouter(self, *, model_name, prompt_payload, timeout):
        with self._lock:
            self._active += 1
            self.calls += 1
            self.peak_concurrency = max(self.peak_concurrency, self._active)
        try:
            time.sleep(self.delay)
        finally:
            with self._lock:
                self._active -= 1
        return {
            "ok": True,
            "parsed_json": {"Q1": 4, "Q2": 3, "Q3": 5},
            "raw_text": "",
            "error": None,
            "status_code": 200,
        }


def test_records_stay_in_respondent_order(legacy):
    """Completion order must not leak into saved output."""
    records, debug = _run(legacy, _RecordingClient(delay=0.0), sample_size=6, max_concurrency=6)

    assert debug["questions_fallback_to_mock"] == 0
    assert debug["questions_parsed_from_live"] == 18

    respondent_order = []
    for record in records:
        if record.respondent_id not in respondent_order:
            respondent_order.append(record.respondent_id)
    assert respondent_order == [f"RESP_{index:03d}" for index in range(1, 7)]

    # Split mode alternates models across respondents; that pairing must hold.
    by_respondent = {record.respondent_id: record.model for record in records}
    assert by_respondent["RESP_001"] == "model-a"
    assert by_respondent["RESP_002"] == "model-b"


def test_requests_actually_overlap(legacy):
    client = _RecordingClient(delay=0.05)
    _run(legacy, client, sample_size=8, max_concurrency=8)

    assert client.calls == 8
    assert client.peak_concurrency > 1, "provider requests were serialized"


def test_concurrency_of_one_still_works(legacy):
    """max_concurrency=1 must fall back to a plain sequential loop."""
    client = _RecordingClient(delay=0.0)
    records, debug = _run(legacy, client, sample_size=4, max_concurrency=1)

    assert client.calls == 4
    assert client.peak_concurrency == 1
    assert debug["questions_parsed_from_live"] == 12
    assert len(records) == 12


def test_parallel_and_sequential_produce_identical_records(legacy):
    sequential, sequential_debug = _run(
        legacy, _RecordingClient(delay=0.0), sample_size=5, max_concurrency=1
    )
    parallel, parallel_debug = _run(
        legacy, _RecordingClient(delay=0.0), sample_size=5, max_concurrency=5
    )

    assert sequential_debug == parallel_debug
    assert [record.model_dump() for record in sequential] == [
        record.model_dump() for record in parallel
    ]
