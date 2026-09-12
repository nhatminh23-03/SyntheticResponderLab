from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.persistence.models import InterviewTurn, Study
from src.services.exceptions import QuotaExceededApiError
from src.services.llm_budget import (
    CLASS_BUDGET_USD,
    CLASS_RUN_CAP,
    RUN_BUDGET_USD,
    LlmBudgetSnapshot,
    class_budget_usd,
    enforce_budget_open,
    enforce_measured_cost,
    enforce_run_preflight,
    load_interview_budget_snapshot,
    lock_class_budget_for_transaction,
    parse_budget_usd,
    resolve_run_budget_usd,
)


def _snapshot(
    *,
    run_spent: str = "0",
    class_spent: str = "0",
    run_budget: str = "0.75",
) -> LlmBudgetSnapshot:
    budget = Decimal(run_budget)
    return LlmBudgetSnapshot(
        run_spent_usd=Decimal(run_spent),
        run_tokens_in=0,
        run_tokens_out=0,
        run_budget_usd=budget,
        class_spent_usd=Decimal(class_spent),
        class_budget_usd=class_budget_usd(budget),
        run_provider_call_count=0,
    )


def test_default_and_environment_budget_values_are_decimal_and_derived_per_class():
    assert RUN_BUDGET_USD == Decimal("0.75")
    assert CLASS_RUN_CAP == 30
    assert CLASS_BUDGET_USD == Decimal("22.50")
    assert resolve_run_budget_usd({}) == RUN_BUDGET_USD
    assert resolve_run_budget_usd({"NEO_LLM_BUDGET_USD": " "}) == RUN_BUDGET_USD
    assert resolve_run_budget_usd({"NEO_LLM_BUDGET_USD": "0"}) == Decimal("0")
    assert class_budget_usd("0.40") == Decimal("12.00")


@pytest.mark.parametrize("value", [True, "not-money", "NaN", "Infinity", "-0.01"])
def test_budget_values_must_be_finite_and_nonnegative(value):
    with pytest.raises(ValueError, match="non-negative dollar amount"):
        parse_budget_usd(value)


def test_preflight_allows_exact_limit_and_reports_over_budget_estimate():
    enforce_run_preflight(estimated_cost_usd="0.75")

    with pytest.raises(QuotaExceededApiError) as caught:
        enforce_run_preflight(estimated_cost_usd="0.7501")

    assert "would cost $0.76" in caught.value.message
    assert caught.value.details == {
        "scope": "run",
        "projected_cost_usd": "0.7501",
        "budget_usd": "0.75",
        "estimated_cost_usd": "0.7501",
    }


def test_preflight_enforces_aggregate_class_cap_and_allows_exact_limit():
    enforce_run_preflight(
        estimated_cost_usd="0.50",
        class_spent_usd="22.00",
    )

    with pytest.raises(QuotaExceededApiError) as caught:
        enforce_run_preflight(
            estimated_cost_usd="0.51",
            class_spent_usd="22.00",
        )

    assert "class spend to $22.51" in caught.value.message
    assert caught.value.details["scope"] == "class"


def test_mid_run_hard_stop_checks_run_before_class_cap():
    with pytest.raises(QuotaExceededApiError) as caught:
        enforce_budget_open(_snapshot(run_spent="0.75", class_spent="22.50"))

    assert caught.value.details["scope"] == "run"
    assert "Budget hard stop" in caught.value.message


def test_mid_run_hard_stop_checks_aggregate_class_cap():
    with pytest.raises(QuotaExceededApiError) as caught:
        enforce_budget_open(_snapshot(run_spent="0.20", class_spent="22.50"))

    assert caught.value.details["scope"] == "class"


def test_measured_cost_allows_exact_run_and_class_limits():
    enforce_measured_cost(
        _snapshot(run_spent="0.70", class_spent="22.45"),
        cost_usd="0.05",
    )


def test_measured_cost_hard_stops_run_overage_before_class_overage():
    with pytest.raises(QuotaExceededApiError) as caught:
        enforce_measured_cost(
            _snapshot(run_spent="0.70", class_spent="22.49"),
            cost_usd="0.06",
        )

    assert caught.value.details["scope"] == "run"
    assert caught.value.details["projected_cost_usd"] == "0.76"
    assert "call cost $0.06" in caught.value.message


def test_measured_cost_hard_stops_class_overage():
    with pytest.raises(QuotaExceededApiError) as caught:
        enforce_measured_cost(
            _snapshot(run_spent="0.20", class_spent="22.49"),
            cost_usd="0.02",
        )

    assert caught.value.details["scope"] == "class"
    assert caught.value.details["projected_cost_usd"] == "22.51"


def test_snapshot_aggregates_one_run_and_the_whole_class(db_session):
    study = Study(
        public_id="study_budget",
        owner_user_id="student",
        owner_org_id=None,
        study_mode="neo_smart",
        lifecycle_status="draft",
    )
    db_session.add(study)
    db_session.flush()
    for session_id, cost, tokens_in, tokens_out in [
        ("session-a", "0.10", 100, 10),
        ("session-a", "0.02", 125, 12),
        ("session-b", "0.30", 300, 30),
    ]:
        db_session.add(
            InterviewTurn(
                study_id=study.id,
                persona_id="neo-001",
                session_id=session_id,
                role="assistant",
                text="Measured answer",
                model="provider/model",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=Decimal(cost),
            )
        )
    db_session.flush()

    snapshot = load_interview_budget_snapshot(
        db_session,
        session_id="session-a",
        run_budget_usd="0.50",
    )

    assert snapshot.run_spent_usd == Decimal("0.12")
    assert snapshot.run_tokens_in == 225
    assert snapshot.run_tokens_out == 22
    assert snapshot.class_spent_usd == Decimal("0.42")
    assert snapshot.run_budget_usd == Decimal("0.50")
    assert snapshot.class_budget_usd == Decimal("15.00")
    assert snapshot.run_provider_call_count == 2


def test_snapshot_includes_paid_ai_interviewer_questions(db_session):
    study = Study(
        public_id="study_interviewer_budget",
        owner_user_id="student",
        owner_org_id=None,
        study_mode="neo_smart",
        lifecycle_status="draft",
    )
    db_session.add(study)
    db_session.flush()
    db_session.add(
        InterviewTurn(
            study_id=study.id,
            persona_id="neo-001",
            session_id="agent-session",
            role="user",
            text="Which part of installation feels uncertain?",
            model="provider/interviewer",
            tokens_in=80,
            tokens_out=9,
            cost_usd=Decimal("0.004"),
        )
    )
    db_session.flush()

    snapshot = load_interview_budget_snapshot(
        db_session,
        session_id="agent-session",
        run_budget_usd="0.75",
    )

    assert snapshot.run_spent_usd == Decimal("0.004")
    assert snapshot.run_tokens_in == 80
    assert snapshot.run_tokens_out == 9
    assert snapshot.run_provider_call_count == 1


def test_postgres_budget_lock_uses_one_class_wide_advisory_lock():
    calls = []

    class RecordingSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

    lock_class_budget_for_transaction(RecordingSession())

    assert len(calls) == 1
    assert "pg_advisory_xact_lock" in calls[0][0]
    assert calls[0][1] == {"lock_id": 6_724_146_956_501_044_844}
