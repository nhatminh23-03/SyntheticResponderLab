from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

import pytest

from conftest import API_ROOT
from src.persistence.persona_seed import EXPECTED_PERSONA_COUNT
from src.services.model_catalog import DEFAULT_INTERVIEW_MODEL_ID


REPO_ROOT = API_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import load_check, prewarm_cache  # noqa: E402


def _args(**overrides) -> argparse.Namespace:
    defaults = {
        "base_url": "http://127.0.0.1:8000",
        "study_id": None,
        "timeout": 1.0,
        "deployment_secret": "",
        "user_id": "load-check",
    }
    return argparse.Namespace(**{**defaults, **overrides})


def test_payload_uses_only_prewarmed_paths_and_blocks_paid_cache_misses():
    payloads = [
        load_check.build_interview_payload(f"P{index:03d}", index)
        for index in range(1, EXPECTED_PERSONA_COUNT + 1)
    ]

    assert all(payload["prompt"] in prewarm_cache.SUGGESTED_QUESTIONS for payload in payloads)
    assert all(payload["model"] == DEFAULT_INTERVIEW_MODEL_ID for payload in payloads)
    assert all(payload["standalone"] is True for payload in payloads)
    assert all(payload["messages"] == [] for payload in payloads)
    assert all(
        payload["estimated_run_cost_usd"] == load_check.CACHE_MISS_GUARD_USD
        for payload in payloads
    )
    assert len({payload["session_id"] for payload in payloads}) == EXPECTED_PERSONA_COUNT


def test_cached_response_requires_an_explicit_hit_and_zero_cost():
    valid = {
        "data": {
            "interview_chat": {
                "cache_hit": True,
                "session_usage": {"cost_usd": "0"},
            }
        }
    }

    assert load_check.validate_cached_response(valid) is None
    assert "not a cache hit" in load_check.validate_cached_response(
        {"data": {"interview_chat": {"cache_hit": False}}}
    )
    assert "valid session cost" in load_check.validate_cached_response(
        {"data": {"interview_chat": {"cache_hit": True, "session_usage": {}}}}
    )
    assert "non-zero" in load_check.validate_cached_response(
        {
            "data": {
                "interview_chat": {
                    "cache_hit": True,
                    "session_usage": {"cost_usd": "0.000001"},
                }
            }
        }
    )
    assert "data.interview_chat" in load_check.validate_cached_response({"data": {}})


def test_nearest_rank_percentiles_and_error_rate_are_reported():
    results = [
        load_check.RequestResult(
            student_number=index,
            persona_id=f"P{index:03d}",
            latency_ms=float(index),
            error="failed" if index in {1, 2, 3} else None,
        )
        for index in range(1, 31)
    ]

    summary = load_check.summarize_results(results)

    assert summary.request_count == 30
    assert summary.success_count == 27
    assert summary.error_count == 3
    assert summary.error_rate_percent == 10.0
    assert summary.p50_ms == 15.0
    assert summary.p95_ms == 29.0
    assert summary.p99_ms == 30.0
    with pytest.raises(ValueError, match="without values"):
        load_check.nearest_rank_percentile([], 50)
    with pytest.raises(ValueError, match="between 1 and 100"):
        load_check.nearest_rank_percentile([1.0], 0)
    with pytest.raises(ValueError, match="empty load check"):
        load_check.summarize_results([])


def test_runner_releases_exactly_30_requests_together():
    persona_ids = [f"P{index:03d}" for index in range(1, 31)]
    requests_started = threading.Barrier(30)
    seen_personas: list[str] = []
    seen_lock = threading.Lock()

    def fake_requester(url, **kwargs):
        assert url.endswith("/interview/chat")
        requests_started.wait(timeout=2)
        with seen_lock:
            seen_personas.append(str(kwargs["payload"]["persona_id"]))
        return {
            "data": {
                "interview_chat": {
                    "cache_hit": True,
                    "session_usage": {"cost_usd": "0"},
                }
            }
        }

    results = load_check.run_concurrent_requests(
        base_url="http://api.test",
        study_id="std_test",
        persona_ids=persona_ids,
        headers={},
        timeout=2,
        requester=fake_requester,
    )

    assert len(results) == 30
    assert all(result.succeeded for result in results)
    assert sorted(seen_personas) == persona_ids
    with pytest.raises(ValueError, match="exactly 30 personas"):
        load_check.run_concurrent_requests(
            base_url="http://api.test",
            study_id="std_test",
            persona_ids=persona_ids[:-1],
            headers={},
            timeout=2,
            requester=fake_requester,
        )


def test_missing_server_exits_safely_with_rerun_instructions(capsys):
    def unavailable(url, **kwargs):
        raise load_check.LoadCheckHttpError("connection refused")

    assert load_check.run(_args(), requester=unavailable) == 2
    output = capsys.readouterr()
    assert "No local API server is reachable" in output.err
    assert "CACHE_MODE=replay_only" in output.err


def test_run_reports_metrics_and_returns_failure_for_any_non_cache_hit(capsys):
    calls: list[str] = []

    def fake_requester(url, **kwargs):
        calls.append(url)
        if url.endswith("/health"):
            return {"data": {"status": "ok"}}
        if url.endswith("/personas"):
            return {
                "data": {
                    "personas": [
                        {"persona_id": f"P{index:03d}"} for index in range(1, 31)
                    ]
                }
            }
        if url.endswith("/studies"):
            return {"data": {"study": {"study_id": "std_test"}}}
        persona_id = str(kwargs["payload"]["persona_id"])
        return {
            "data": {
                "interview_chat": {
                    "cache_hit": persona_id != "P030",
                    "session_usage": {"cost_usd": "0"},
                }
            }
        }

    assert load_check.run(_args(), requester=fake_requester) == 1
    output = capsys.readouterr()
    assert "Concurrent students: 30" in output.out
    assert "p50 latency:" in output.out
    assert "p95 latency:" in output.out
    assert "p99 latency:" in output.out
    assert "Error rate: 3.3% (1/30)" in output.out
    assert "student 30 / P030: response was not a cache hit" in output.out
    assert any(url.endswith("/studies") for url in calls)


def test_existing_study_skips_creation_and_all_cache_hits_pass(capsys):
    def fake_requester(url, **kwargs):
        if url.endswith("/health"):
            return {}
        if url.endswith("/personas"):
            return {
                "data": {
                    "personas": [
                        {"persona_id": f"P{index:03d}"} for index in range(1, 31)
                    ]
                }
            }
        assert "/studies/std_existing/interview/chat" in url
        return {
            "data": {
                "interview_chat": {
                    "cache_hit": True,
                    "session_usage": {"cost_usd": "0"},
                }
            }
        }

    assert load_check.run(_args(study_id="std_existing"), requester=fake_requester) == 0
    assert "Error rate: 0.0% (0/30)" in capsys.readouterr().out


def test_setup_validation_and_timeout_fail_without_starting_load(capsys):
    assert load_check.run(_args(timeout=0), requester=lambda *args, **kwargs: {}) == 2
    assert "--timeout must be positive" in capsys.readouterr().err

    def incomplete_personas(url, **kwargs):
        if url.endswith("/health"):
            return {}
        return {"data": {"personas": [{"persona_id": "P001"}]}}

    assert load_check.run(_args(), requester=incomplete_personas) == 2
    assert "API returned 1" in capsys.readouterr().err
