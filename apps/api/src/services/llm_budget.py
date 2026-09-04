"""Hard spend limits for classroom LLM interview runs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_UP
from typing import Final, Mapping

from sqlalchemy import Text, cast, select, text
from sqlalchemy.orm import Session

from src.persistence.models import InterviewTurn
from src.services.exceptions import QuotaExceededApiError


RUN_BUDGET_USD: Final[Decimal] = Decimal("0.75")
CLASS_RUN_CAP: Final[int] = 30
CLASS_BUDGET_USD: Final[Decimal] = RUN_BUDGET_USD * CLASS_RUN_CAP
BUDGET_ENV_VAR: Final[str] = "NEO_LLM_BUDGET_USD"

_ZERO_USD = Decimal("0")
_CENT = Decimal("0.01")
_CLASS_BUDGET_LOCK_ID: Final[int] = 6_724_146_956_501_044_844


@dataclass(frozen=True)
class LlmBudgetSnapshot:
    run_spent_usd: Decimal
    run_budget_usd: Decimal
    class_spent_usd: Decimal
    class_budget_usd: Decimal
    run_provider_call_count: int


def parse_budget_usd(value: object, *, name: str = "budget") -> Decimal:
    """Return a finite, non-negative dollar amount without float arithmetic."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative dollar amount.")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be a non-negative dollar amount.") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{name} must be a non-negative dollar amount.")
    return amount


def resolve_run_budget_usd(
    environ: Mapping[str, str] | None = None,
) -> Decimal:
    """Resolve the per-run cap, including the zero-dollar kill switch."""
    source = os.environ if environ is None else environ
    configured = source.get(BUDGET_ENV_VAR)
    if configured is None or not configured.strip():
        return RUN_BUDGET_USD
    return parse_budget_usd(configured, name=BUDGET_ENV_VAR)


def class_budget_usd(run_budget_usd: object = RUN_BUDGET_USD) -> Decimal:
    """Derive the aggregate cap for a class of 30 from the per-run cap."""
    return parse_budget_usd(run_budget_usd, name="run budget") * CLASS_RUN_CAP


def lock_class_budget_for_transaction(session: Session) -> None:
    """Serialize paid-call authorization on PostgreSQL.

    The lock remains held through the provider call and measured-cost insert,
    preventing two concurrent cache misses from both spending the final class
    allowance. SQLite is used only for local/test operation and serializes
    writes itself.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": _CLASS_BUDGET_LOCK_ID},
    )


def load_interview_budget_snapshot(
    session: Session,
    *,
    session_id: str,
    run_budget_usd: object = RUN_BUDGET_USD,
) -> LlmBudgetSnapshot:
    """Load measured spend for one interview run and the whole class."""
    run_budget = parse_budget_usd(run_budget_usd, name="run budget")
    run_usage = session.execute(
        select(
            cast(InterviewTurn.cost_usd, Text),
            InterviewTurn.tokens_in,
            InterviewTurn.tokens_out,
        ).where(
            InterviewTurn.session_id == session_id,
            InterviewTurn.role == "assistant",
        )
    ).all()
    class_costs = session.scalars(select(cast(InterviewTurn.cost_usd, Text))).all()
    run_spent = sum((Decimal(row[0]) for row in run_usage), start=_ZERO_USD)
    class_spent = sum((Decimal(cost) for cost in class_costs), start=_ZERO_USD)
    run_provider_call_count = sum(
        Decimal(row[0]) > 0 or row[1] > 0 or row[2] > 0
        for row in run_usage
    )
    return LlmBudgetSnapshot(
        run_spent_usd=Decimal(run_spent),
        run_budget_usd=run_budget,
        class_spent_usd=class_spent,
        class_budget_usd=class_budget_usd(run_budget),
        run_provider_call_count=run_provider_call_count,
    )


def enforce_run_preflight(
    *,
    estimated_cost_usd: object,
    class_spent_usd: object = _ZERO_USD,
    run_budget_usd: object = RUN_BUDGET_USD,
) -> None:
    """Refuse a new run whose estimate exceeds either hard cap."""
    estimated = parse_budget_usd(estimated_cost_usd, name="estimated run cost")
    run_budget = parse_budget_usd(run_budget_usd, name="run budget")
    class_spent = parse_budget_usd(class_spent_usd, name="class spend")
    aggregate_budget = class_budget_usd(run_budget)

    if estimated > run_budget:
        raise QuotaExceededApiError(
            f"This run would cost {_format_usd(estimated)}, exceeding its "
            f"{_format_usd(run_budget)} budget, so it was not started.",
            details=_budget_details(
                scope="run",
                projected=estimated,
                limit=run_budget,
                estimated_cost=estimated,
            ),
        )

    projected_class_spend = class_spent + estimated
    if projected_class_spend > aggregate_budget:
        raise QuotaExceededApiError(
            f"This run would bring class spend to {_format_usd(projected_class_spend)}, "
            f"exceeding the {_format_usd(aggregate_budget)} class budget, so it was not started.",
            details=_budget_details(
                scope="class",
                projected=projected_class_spend,
                limit=aggregate_budget,
                estimated_cost=estimated,
            ),
        )


def enforce_budget_open(snapshot: LlmBudgetSnapshot) -> None:
    """Hard-stop before another paid call once a measured cap is exhausted."""
    if snapshot.run_spent_usd >= snapshot.run_budget_usd:
        raise QuotaExceededApiError(
            f"Budget hard stop: this run has spent {_format_usd(snapshot.run_spent_usd)} "
            f"of its {_format_usd(snapshot.run_budget_usd)} budget.",
            details=_budget_details(
                scope="run",
                projected=snapshot.run_spent_usd,
                limit=snapshot.run_budget_usd,
            ),
        )
    if snapshot.class_spent_usd >= snapshot.class_budget_usd:
        raise QuotaExceededApiError(
            f"Budget hard stop: the class has spent {_format_usd(snapshot.class_spent_usd)} "
            f"of its {_format_usd(snapshot.class_budget_usd)} aggregate budget.",
            details=_budget_details(
                scope="class",
                projected=snapshot.class_spent_usd,
                limit=snapshot.class_budget_usd,
            ),
        )


def enforce_measured_cost(
    snapshot: LlmBudgetSnapshot,
    *,
    cost_usd: object,
) -> None:
    """Hard-stop a run after a call reports cost beyond either allowance."""
    measured_cost = parse_budget_usd(cost_usd, name="measured call cost")
    projected_run_spend = snapshot.run_spent_usd + measured_cost
    if projected_run_spend > snapshot.run_budget_usd:
        raise QuotaExceededApiError(
            f"Budget hard stop: this call cost {_format_usd(measured_cost)} and would bring "
            f"the run to {_format_usd(projected_run_spend)}, exceeding its "
            f"{_format_usd(snapshot.run_budget_usd)} budget.",
            details=_budget_details(
                scope="run",
                projected=projected_run_spend,
                limit=snapshot.run_budget_usd,
                measured_cost=measured_cost,
            ),
        )

    projected_class_spend = snapshot.class_spent_usd + measured_cost
    if projected_class_spend > snapshot.class_budget_usd:
        raise QuotaExceededApiError(
            f"Budget hard stop: this call cost {_format_usd(measured_cost)} and would bring "
            f"class spend to {_format_usd(projected_class_spend)}, exceeding the "
            f"{_format_usd(snapshot.class_budget_usd)} aggregate budget.",
            details=_budget_details(
                scope="class",
                projected=projected_class_spend,
                limit=snapshot.class_budget_usd,
                measured_cost=measured_cost,
            ),
        )


def _format_usd(value: Decimal) -> str:
    rounded_up = value.quantize(_CENT, rounding=ROUND_UP)
    return f"${rounded_up:.2f}"


def _budget_details(
    *,
    scope: str,
    projected: Decimal,
    limit: Decimal,
    estimated_cost: Decimal | None = None,
    measured_cost: Decimal | None = None,
) -> dict[str, str]:
    details = {
        "scope": scope,
        "projected_cost_usd": str(projected),
        "budget_usd": str(limit),
    }
    if estimated_cost is not None:
        details["estimated_cost_usd"] = str(estimated_cost)
    if measured_cost is not None:
        details["measured_cost_usd"] = str(measured_cost)
    return details
