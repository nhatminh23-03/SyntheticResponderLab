#!/usr/bin/env python3
"""Pre-warm the standalone interview cache for the fixed classroom personas.

Run from the repository root:

    python scripts/prewarm_cache.py --dry-run
    python scripts/prewarm_cache.py --max-usd 2.00

The dry run reads only persona and cache metadata. The live command uses the same
prompt builder, model, and cache-key inputs as the standalone interview endpoint.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session


REPO_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = REPO_ROOT / "apps/api"
sys.path.insert(0, str(API_ROOT))

from src.config.settings import AppSettings, get_settings  # noqa: E402
from src.persistence.models import InterviewCacheEntry, Persona  # noqa: E402
from src.persistence.persona_seed import EXPECTED_PERSONA_COUNT  # noqa: E402
from src.persistence.session import create_session_factory  # noqa: E402
from src.services.interview_cache import (  # noqa: E402
    CACHE_FIRST,
    InterviewAnswer,
    build_interview_cache_key,
    hash_prior_turns,
    resolve_interview_answer,
)
from src.services.interview_service import (  # noqa: E402
    _build_fixed_persona_system_prompt,
    _call_openrouter_messages,
)
from src.services.model_catalog import list_interview_model_catalog  # noqa: E402


DEFAULT_MAX_USD = Decimal("2.00")
SUGGESTED_QUESTIONS = (
    "What is your first reaction to the Tahoe Mini, and what would you use it for?",
    "What would stop you from buying one?",
    "Walk me through how you'd actually decide on something like this.",
    "Who else in your household would have a say?",
)


@dataclass(frozen=True)
class PrewarmPath:
    persona_id: str
    question: str
    prior_turns: tuple[dict[str, str], ...]
    cache_hit: bool


@dataclass(frozen=True)
class PrewarmPlan:
    model_id: str
    model_name: str
    estimated_cost_per_call_usd: Decimal
    paths: tuple[PrewarmPath, ...]

    @property
    def cached_count(self) -> int:
        return sum(path.cache_hit for path in self.paths)

    @property
    def provider_call_count(self) -> int:
        return len(self.paths) - self.cached_count

    @property
    def projected_cost_usd(self) -> Decimal:
        return self.estimated_cost_per_call_usd * self.provider_call_count


class PrewarmBudgetExceededError(RuntimeError):
    """Raised when another warm-up provider call would violate the spend cap."""


def parse_usd(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a valid USD amount") from exc
    if not amount.is_finite() or amount < 0:
        raise argparse.ArgumentTypeError("must be a finite, non-negative USD amount")
    return amount


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cache the four classroom suggested questions for all 30 fixed personas "
            "on the cheapest curated interview model."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the projected provider spend without making provider calls or writes.",
    )
    parser.add_argument(
        "--max-usd",
        type=parse_usd,
        default=DEFAULT_MAX_USD,
        help="Set the live spend cap; preflight uses projected cost (default: 2.00).",
    )
    return parser


def _cheapest_model() -> dict[str, object]:
    models = list_interview_model_catalog()["models"]
    return min(
        models,
        key=lambda model: Decimal(str(model["estimated_cost_per_persona_usd"])),
    )


def build_prewarm_plan(session: Session) -> PrewarmPlan:
    personas = session.scalars(select(Persona).order_by(Persona.row_index)).all()
    if len(personas) != EXPECTED_PERSONA_COUNT:
        raise RuntimeError(
            "Pre-warm requires exactly "
            f"{EXPECTED_PERSONA_COUNT} database personas; found {len(personas)}."
        )

    model = _cheapest_model()
    model_id = str(model["id"])
    paths: list[PrewarmPath] = []
    for persona in personas:
        system_prompt = _build_fixed_persona_system_prompt(dict(persona.profile_json))
        prior_turns = ({"role": "system", "content": system_prompt},)
        prior_turn_hash = hash_prior_turns(prior_turns)
        for question in SUGGESTED_QUESTIONS:
            cache_key = build_interview_cache_key(
                persona_id=persona.persona_id,
                model=model_id,
                question=question,
                prior_turn_hash=prior_turn_hash,
            )
            paths.append(
                PrewarmPath(
                    persona_id=persona.persona_id,
                    question=question,
                    prior_turns=prior_turns,
                    cache_hit=session.get(InterviewCacheEntry, cache_key) is not None,
                )
            )

    return PrewarmPlan(
        model_id=model_id,
        model_name=str(model["name"]),
        estimated_cost_per_call_usd=Decimal(
            str(model["estimated_cost_per_persona_usd"])
        ),
        paths=tuple(paths),
    )


def warm_cache(
    session: Session,
    *,
    plan: PrewarmPlan,
    api_key: str,
    call_openrouter: Callable[..., InterviewAnswer] = _call_openrouter_messages,
    record_spend: Callable[[Decimal], None] | None = None,
    max_measured_usd: Decimal | None = None,
) -> Decimal:
    measured_spend = Decimal("0")
    for path in plan.paths:
        if path.cache_hit:
            continue

        messages = [*path.prior_turns, {"role": "user", "content": path.question}]

        def call_provider() -> InterviewAnswer:
            nonlocal measured_spend
            if (
                max_measured_usd is not None
                and measured_spend + plan.estimated_cost_per_call_usd > max_measured_usd
            ):
                raise PrewarmBudgetExceededError(
                    "Refusing another provider call: measured spend plus the next "
                    f"estimated call would exceed ${max_measured_usd:.6f}."
                )
            answer = call_openrouter(
                api_key=api_key,
                model=plan.model_id,
                messages=messages,
                timeout=90,
            )
            measured_spend += answer.cost_usd
            if record_spend is not None:
                record_spend(answer.cost_usd)
            return answer

        resolve_interview_answer(
            session,
            cache_mode=CACHE_FIRST,
            persona_id=path.persona_id,
            model=plan.model_id,
            question=path.question,
            prior_turns=path.prior_turns,
            call_provider=call_provider,
        )
        session.commit()
        if max_measured_usd is not None and measured_spend > max_measured_usd:
            raise PrewarmBudgetExceededError(
                "Warm-up hard stop: measured spend "
                f"${measured_spend:.6f} exceeded ${max_measured_usd:.6f}. "
                "The paid response was cached, but no further calls were made."
            )
    return measured_spend


def _print_plan(plan: PrewarmPlan, max_usd: Decimal) -> None:
    print(f"Personas: {EXPECTED_PERSONA_COUNT}")
    print(f"Suggested questions: {len(SUGGESTED_QUESTIONS)}")
    print(
        f"Cache paths: {len(plan.paths)} "
        f"({plan.cached_count} cached, {plan.provider_call_count} provider calls projected)"
    )
    print(f"Model: {plan.model_name} ({plan.model_id})")
    print(f"Projected cost: ${plan.projected_cost_usd:.6f} (limit: ${max_usd:.2f})")


def run(args: argparse.Namespace, settings: AppSettings) -> int:
    session_factory = create_session_factory(settings)
    with session_factory() as session:
        plan = build_prewarm_plan(session)
        _print_plan(plan, args.max_usd)

        if plan.projected_cost_usd > args.max_usd:
            print(
                "Refusing to run: projected cost "
                f"${plan.projected_cost_usd:.6f} exceeds --max-usd ${args.max_usd:.2f}.",
                file=sys.stderr,
            )
            return 2
        if args.dry_run:
            print("Dry run complete; no provider calls or cache writes were made.")
            return 0

        api_key = (settings.openrouter_api_key or "").strip()
        if not api_key:
            print("Refusing to run: OPENROUTER_API_KEY is not configured.", file=sys.stderr)
            print("Measured spend: $0.000000")
            return 2
        if settings.llm_budget_usd == 0:
            print("Refusing to run: NEO_LLM_BUDGET_USD kill switch is set to 0.", file=sys.stderr)
            print("Measured spend: $0.000000")
            return 2
        if plan.projected_cost_usd > settings.llm_budget_usd:
            print(
                "Refusing to run: projected cost "
                f"${plan.projected_cost_usd:.6f} exceeds NEO_LLM_BUDGET_USD "
                f"${settings.llm_budget_usd:.2f}.",
                file=sys.stderr,
            )
            print("Measured spend: $0.000000")
            return 2

        measured_spend = Decimal("0")
        live_cap_usd = min(args.max_usd, settings.llm_budget_usd)

        def record_spend(cost_usd: Decimal) -> None:
            nonlocal measured_spend
            measured_spend += cost_usd

        try:
            warm_cache(
                session,
                plan=plan,
                api_key=api_key,
                record_spend=record_spend,
                max_measured_usd=live_cap_usd,
            )
        except PrewarmBudgetExceededError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        finally:
            print(f"Measured spend: ${measured_spend:.6f}")
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Relative SQLite URLs in apps/api/.env are intentionally rooted at apps/api.
    os.chdir(API_ROOT)
    return run(args, get_settings())


if __name__ == "__main__":
    raise SystemExit(main())
