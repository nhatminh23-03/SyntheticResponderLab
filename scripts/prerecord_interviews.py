#!/usr/bin/env python3
"""Record complete adaptive interviews in the app database without a web server.

    python scripts/prerecord_interviews.py --dry-run
    python scripts/prerecord_interviews.py --personas 3 --max-usd 0.50

Each model plays both roles. The fixed public-data personas and the brief below
are the only research inputs; no human survey responses are loaded. Replay the
saved questions through the standalone service with the same persona/model/history,
or rerun this command to reuse both agents' caches. Estimates assume cache misses
because later questions depend on answers that do not yet exist.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = REPO_ROOT / "apps/api"
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from scripts.prewarm_cache import DEFAULT_MAX_USD, parse_usd  # noqa: E402
from src.config.settings import AppSettings, get_settings  # noqa: E402
from src.persistence.models import InterviewTurn, Persona, Study  # noqa: E402
from src.persistence.session import create_session_factory  # noqa: E402
from src.services.exceptions import ApiError, QuotaExceededApiError  # noqa: E402
from src.services.ids import make_public_id  # noqa: E402
from src.services.interview_cache import CACHE_FIRST, REPLAY_ONLY  # noqa: E402
from src.services.interview_service import (  # noqa: E402
    continue_standalone_interview_chat,
    generate_interviewer_question,
    save_research_brief,
)
from src.services.interviewer_agent import derive_interviewer_turn_plan  # noqa: E402
from src.services.llm_budget import (  # noqa: E402
    enforce_run_preflight,
    load_interview_budget_snapshot,
)
from src.services.model_catalog import (  # noqa: E402
    DEFAULT_INTERVIEW_PERSONAS,
    MAX_INTERVIEW_PERSONAS,
    MIN_INTERVIEW_PERSONAS,
    list_interview_model_catalog,
)

DEFAULT_MODELS = ("deepseek/deepseek-v4-pro", "qwen/qwen3.7-plus")
RESEARCH_BRIEF = {
    "primary_question": "How would homeowners decide whether to buy a Tahoe Mini backyard studio?",
    "known_context": "Tahoe Mini is a compact modular backyard studio for flexible household use.",
    "decisions_to_inform": ["Understand uses, purchase barriers, and household decision making."],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Project spend without provider calls or writes.")
    parser.add_argument("--max-usd", type=parse_usd, default=DEFAULT_MAX_USD,
                        help="Total batch spend cap (default: 2.00); run/class caps also apply.")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS),
                        choices=[model["id"] for model in list_interview_model_catalog()["models"]])
    parser.add_argument("--personas", type=int, default=DEFAULT_INTERVIEW_PERSONAS,
                        choices=range(MIN_INTERVIEW_PERSONAS, MAX_INTERVIEW_PERSONAS + 1))
    return parser


def _batch_spend(session: Session, session_ids: list[str]) -> Decimal:
    return sum(
        (load_interview_budget_snapshot(session, session_id=value).run_spent_usd
         for value in session_ids),
        start=Decimal("0"),
    )


def _check_batch_cap(session: Session, session_ids: list[str], max_usd: Decimal,
                     next_estimate: Decimal = Decimal("0")) -> None:
    if _batch_spend(session, session_ids) + next_estimate > max_usd:
        raise QuotaExceededApiError(
            f"Batch hard stop: measured spend plus next estimated call exceeds --max-usd ${max_usd:.6f}. "
            "Paid turns remain saved; no further calls were made."
        )


def _print_summary(session: Session, runs: dict[str, str]) -> None:
    for model, session_id in runs.items():
        turns = session.scalars(select(InterviewTurn).where(InterviewTurn.session_id == session_id)).all()
        usage = load_interview_budget_snapshot(session, session_id=session_id)
        print(f"{model}: turns={sum(turn.role == 'assistant' for turn in turns)}, "
              f"tokens_in={usage.run_tokens_in}, tokens_out={usage.run_tokens_out}, "
              f"measured_usd=${usage.run_spent_usd:.6f}, session_id={session_id}")


def run(args: argparse.Namespace, settings: AppSettings) -> int:
    # Recording must populate the cache even when the app is configured "off";
    # preserve replay-only mode so it can never authorize a paid cache miss.
    if settings.cache_mode != REPLAY_ONLY:
        settings = settings.model_copy(update={"cache_mode": CACHE_FIRST})
    replay_only = settings.cache_mode == REPLAY_ONLY
    session_factory = create_session_factory(settings)
    with session_factory() as session:
        runs = {model: make_public_id("ses") for model in args.models}
        try:
            plans = {model: derive_interviewer_turn_plan(
                persona_count=args.personas, interviewer_model=model, interviewee_model=model,
            ) for model in runs}
            personas = session.scalars(select(Persona).order_by(Persona.row_index).limit(args.personas)).all()
            if len(personas) != args.personas:
                raise ValueError(f"Requires {args.personas} database personas; found {len(personas)}.")
            estimates = {model: Decimal("0") if replay_only else plan.estimated_run_cost_usd
                         for model, plan in plans.items()}
            projected = sum(estimates.values(), start=Decimal("0"))
            for model, plan in plans.items():
                print(f"{model}: personas={len(personas)}, turns/persona={plan.turn_limit}, "
                      f"projected_usd=${estimates[model]:.6f}")
            assumption = "replay only; cache misses stop" if replay_only else "assumes cache misses"
            print(f"Projected cost: ${projected:.6f} (limit: ${args.max_usd:.2f}; {assumption})")
            if projected > args.max_usd:
                raise ValueError("Refusing to run: projected cost exceeds --max-usd.")
            if args.dry_run:
                print("Dry run complete; no provider calls or database writes were made.")
                return 0

            # Check all models before creating a study or spending anything. Each
            # model batch is a run; all runs share the existing class allowance.
            class_spent = load_interview_budget_snapshot(session, session_id="").class_spent_usd
            # Replay-only cache misses cannot call a provider, including when
            # the run/class allowance has already been exhausted.
            for plan in (() if replay_only else plans.values()):
                enforce_run_preflight(estimated_cost_usd=plan.estimated_run_cost_usd,
                                      class_spent_usd=class_spent, run_budget_usd=settings.llm_budget_usd)
                class_spent += plan.estimated_run_cost_usd

            study = Study(public_id=make_public_id("std"), lifecycle_status="draft")
            session.add(study)
            session.flush()
            save_research_brief(session, study, RESEARCH_BRIEF)
            print(f"Saved study: {study.public_id}")
            for model, session_id in runs.items():
                plan = plans[model]
                next_estimate = estimates[model] / (len(personas) * plan.turn_limit * 2)
                for persona in personas:
                    history: list[dict[str, str]] = []
                    payload = {"persona_id": persona.persona_id, "session_id": session_id,
                               "persona_count": len(personas), "interviewer_model": model,
                               "interviewee_model": model, "model": model,
                               "allow_expensive_models": True, "messages": history}
                    for _ in range(plan.turn_limit):
                        _check_batch_cap(session, list(runs.values()), args.max_usd, next_estimate)
                        question = generate_interviewer_question(session, settings, study, payload)["question"]
                        _check_batch_cap(session, list(runs.values()), args.max_usd, next_estimate)
                        answer = continue_standalone_interview_chat(
                            session, settings, study, {**payload, "prompt": question},
                        )["reply"]
                        history.extend([{"role": "user", "content": question},
                                        {"role": "assistant", "content": answer}])
                        _check_batch_cap(session, list(runs.values()), args.max_usd)
            return 0
        except (ApiError, ValueError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        finally:
            _print_summary(session, runs)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    os.chdir(API_ROOT)
    return run(args, get_settings())


if __name__ == "__main__":
    raise SystemExit(main())
