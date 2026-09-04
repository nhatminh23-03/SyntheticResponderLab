from __future__ import annotations

import os
import subprocess
import sys
from argparse import ArgumentTypeError, Namespace
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import API_ROOT
from src.persistence.models import Persona
from src.persistence.persona_seed import load_persona_seed_rows
from src.services.interview_cache import InterviewAnswer
from src.services.model_catalog import DEFAULT_INTERVIEW_MODEL_ID


REPO_ROOT = API_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import prewarm_cache  # noqa: E402


def _seed_personas(session) -> None:
    for row in load_persona_seed_rows():
        session.add(Persona(**row))
    session.commit()


def test_plan_covers_every_suggested_question_and_only_projects_cache_misses(db_session):
    _seed_personas(db_session)
    initial = prewarm_cache.build_prewarm_plan(db_session)
    first_path = initial.paths[0]

    def fake_openrouter(**kwargs) -> InterviewAnswer:
        assert kwargs["model"] == DEFAULT_INTERVIEW_MODEL_ID
        assert kwargs["messages"][-1] == {
            "role": "user",
            "content": first_path.question,
        }
        return InterviewAnswer(
            text="A measured synthetic answer.",
            model=DEFAULT_INTERVIEW_MODEL_ID,
            tokens_in=123,
            tokens_out=45,
            cost_usd=Decimal("0.000123"),
        )

    one_path_plan = prewarm_cache.PrewarmPlan(
        model_id=initial.model_id,
        model_name=initial.model_name,
        estimated_cost_per_call_usd=initial.estimated_cost_per_call_usd,
        paths=(first_path,),
    )
    recorded_spend = []
    measured = prewarm_cache.warm_cache(
        db_session,
        plan=one_path_plan,
        api_key="test-key",
        call_openrouter=fake_openrouter,
        record_spend=recorded_spend.append,
    )
    updated = prewarm_cache.build_prewarm_plan(db_session)

    expected_path_count = 30 * len(prewarm_cache.SUGGESTED_QUESTIONS)
    assert initial.model_id == DEFAULT_INTERVIEW_MODEL_ID
    assert len(initial.paths) == expected_path_count == 120
    assert initial.cached_count == 0
    assert initial.provider_call_count == 120
    assert initial.projected_cost_usd == initial.estimated_cost_per_call_usd * 120
    assert measured == Decimal("0.000123")
    assert recorded_spend == [Decimal("0.000123")]
    assert updated.cached_count == 1
    assert updated.provider_call_count == 119
    assert updated.projected_cost_usd == updated.estimated_cost_per_call_usd * 119


def test_plan_refuses_a_database_without_all_30_personas(db_session):
    with pytest.raises(RuntimeError, match="requires exactly 30 database personas; found 0"):
        prewarm_cache.build_prewarm_plan(db_session)


def test_usd_parser_rejects_negative_and_non_finite_limits():
    assert prewarm_cache.parse_usd("2.50") == Decimal("2.50")
    for invalid in ("-0.01", "NaN", "Infinity", "not-money"):
        with pytest.raises(ArgumentTypeError, match="USD amount"):
            prewarm_cache.parse_usd(invalid)


def test_script_questions_match_the_interview_page_suggestions():
    page_source = (REPO_ROOT / "apps/web/src/app/interview/page.tsx").read_text()
    for question in prewarm_cache.SUGGESTED_QUESTIONS:
        assert f'  "{question}",' in page_source


def test_cli_dry_run_projects_cost_and_low_limit_refuses_without_provider_calls(
    tmp_path: Path,
    test_settings,
):
    database_path = tmp_path / "prewarm.db"
    settings = test_settings.model_copy(
        update={"database_url": f"sqlite:///{database_path}"}
    )
    session_factory = prewarm_cache.create_session_factory(settings)
    from src.persistence.base import Base

    engine = session_factory.kw["bind"]
    Base.metadata.create_all(bind=engine)
    with session_factory() as session:
        _seed_personas(session)

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env.pop("OPENROUTER_API_KEY", None)
    command = [sys.executable, str(REPO_ROOT / "scripts/prewarm_cache.py"), "--dry-run"]

    dry_run = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    refused = subprocess.run(
        [*command, "--max-usd", "0.01"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert dry_run.returncode == 0
    assert "Cache paths: 120 (0 cached, 120 provider calls projected)" in dry_run.stdout
    assert "Projected cost: $0.216000 (limit: $2.00)" in dry_run.stdout
    assert "no provider calls or cache writes were made" in dry_run.stdout
    assert refused.returncode == 2
    assert "Projected cost: $0.216000 (limit: $0.01)" in refused.stdout
    assert "Refusing to run: projected cost" in refused.stderr


def test_live_configuration_refuses_missing_key_and_budget_kill_switch(
    db_session,
    test_settings,
    capsys,
):
    _seed_personas(db_session)
    database_url = str(db_session.get_bind().url)
    args = Namespace(dry_run=False, max_usd=Decimal("2.00"))

    missing_key = test_settings.model_copy(
        update={"database_url": database_url, "openrouter_api_key": None}
    )
    assert prewarm_cache.run(args, missing_key) == 2
    missing_output = capsys.readouterr()
    assert "OPENROUTER_API_KEY is not configured" in missing_output.err
    assert "Measured spend: $0.000000" in missing_output.out

    killed = test_settings.model_copy(
        update={
            "database_url": database_url,
            "openrouter_api_key": "test-key",
            "llm_budget_usd": Decimal("0"),
        }
    )
    assert prewarm_cache.run(args, killed) == 2
    killed_output = capsys.readouterr()
    assert "NEO_LLM_BUDGET_USD kill switch is set to 0" in killed_output.err
    assert "Measured spend: $0.000000" in killed_output.out


def test_live_configuration_refuses_positive_budget_below_projection(
    db_session,
    test_settings,
    capsys,
    monkeypatch,
):
    _seed_personas(db_session)
    settings = test_settings.model_copy(
        update={
            "database_url": str(db_session.get_bind().url),
            "openrouter_api_key": "test-key",
            "llm_budget_usd": Decimal("0.01"),
        }
    )

    def unexpected_warm(*_args, **_kwargs):
        pytest.fail("warm_cache must not run after the configured budget refuses the plan")

    monkeypatch.setattr(prewarm_cache, "warm_cache", unexpected_warm)

    result = prewarm_cache.run(
        Namespace(dry_run=False, max_usd=Decimal("2.00")),
        settings,
    )

    output = capsys.readouterr()
    assert result == 2
    assert "exceeds NEO_LLM_BUDGET_USD $0.01" in output.err
    assert output.out.rstrip().endswith("Measured spend: $0.000000")


def test_measured_cap_stops_after_caching_the_paid_response(db_session):
    _seed_personas(db_session)
    initial = prewarm_cache.build_prewarm_plan(db_session)
    two_path_plan = prewarm_cache.PrewarmPlan(
        model_id=initial.model_id,
        model_name=initial.model_name,
        estimated_cost_per_call_usd=Decimal("0.001"),
        paths=initial.paths[:2],
    )
    provider_calls = 0

    def expensive_openrouter(**_kwargs) -> InterviewAnswer:
        nonlocal provider_calls
        provider_calls += 1
        return InterviewAnswer(
            text="A paid answer that crossed the cap.",
            model=initial.model_id,
            tokens_in=123,
            tokens_out=45,
            cost_usd=Decimal("0.006"),
        )

    with pytest.raises(prewarm_cache.PrewarmBudgetExceededError, match="no further calls"):
        prewarm_cache.warm_cache(
            db_session,
            plan=two_path_plan,
            api_key="test-key",
            call_openrouter=expensive_openrouter,
            max_measured_usd=Decimal("0.005"),
        )

    updated = prewarm_cache.build_prewarm_plan(db_session)
    assert provider_calls == 1
    assert updated.cached_count == 1


def test_successful_live_path_prints_measured_spend(
    db_session,
    test_settings,
    capsys,
    monkeypatch,
):
    _seed_personas(db_session)
    settings = test_settings.model_copy(
        update={
            "database_url": str(db_session.get_bind().url),
            "openrouter_api_key": "test-key",
        }
    )

    def fake_warm_cache(*_args, record_spend, **_kwargs):
        record_spend(Decimal("0.001234"))
        return Decimal("0.001234")

    monkeypatch.setattr(prewarm_cache, "warm_cache", fake_warm_cache)

    result = prewarm_cache.run(
        Namespace(dry_run=False, max_usd=Decimal("2.00")),
        settings,
    )

    assert result == 0
    assert capsys.readouterr().out.rstrip().endswith("Measured spend: $0.001234")
