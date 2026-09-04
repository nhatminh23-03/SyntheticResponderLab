"""Durable cache for individual synthetic-persona interview answers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Final, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.persistence.models import InterviewCacheEntry

CACHE_FIRST: Final[str] = "cache_first"
REPLAY_ONLY: Final[str] = "replay_only"
CACHE_OFF: Final[str] = "off"
CACHE_MODES: Final[frozenset[str]] = frozenset({CACHE_FIRST, REPLAY_ONLY, CACHE_OFF})
CACHE_MODE: Final[str] = CACHE_FIRST


@dataclass(frozen=True)
class InterviewAnswer:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    cache_hit: bool = False


class ReplayOnlyCacheMissError(RuntimeError):
    """Raised when replay-only mode cannot satisfy an interview question."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_cache_mode(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in CACHE_MODES:
        allowed = ", ".join(sorted(CACHE_MODES))
        raise ValueError(f"CACHE_MODE must be one of: {allowed}.")
    return normalized


def hash_prior_turns(prior_turns: Sequence[Mapping[str, Any]]) -> str:
    canonical_turns = [
        {
            "role": str(turn.get("role") or ""),
            "content": str(turn.get("content") or ""),
        }
        for turn in prior_turns
    ]
    payload = json.dumps(
        canonical_turns,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_interview_cache_key(
    *,
    persona_id: str,
    model: str,
    question: str,
    prior_turn_hash: str,
) -> str:
    payload = json.dumps(
        {
            "persona_id": persona_id,
            "model": model,
            "question": question,
            "prior_turn_hash": prior_turn_hash,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _lock_cache_key_for_transaction(session: Session, cache_key: str) -> None:
    """Serialize cache resolution for one key on the production database.

    Without this lock, concurrent misses can both call the provider before either
    transaction inserts the cache row. PostgreSQL transaction-scoped advisory
    locks are released automatically on commit or rollback.
    """
    if session.get_bind().dialect.name != "postgresql":
        return

    lock_id = int.from_bytes(bytes.fromhex(cache_key)[:8], byteorder="big", signed=True)
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": lock_id},
    )


def resolve_interview_answer(
    session: Session,
    *,
    cache_mode: str,
    persona_id: str,
    model: str,
    question: str,
    prior_turns: Sequence[Mapping[str, Any]],
    call_provider: Callable[[], InterviewAnswer],
) -> InterviewAnswer:
    mode = normalize_cache_mode(cache_mode)
    prior_turn_hash = hash_prior_turns(prior_turns)
    cache_key = build_interview_cache_key(
        persona_id=persona_id,
        model=model,
        question=question,
        prior_turn_hash=prior_turn_hash,
    )

    if mode != CACHE_OFF:
        _lock_cache_key_for_transaction(session, cache_key)
        cached = session.get(InterviewCacheEntry, cache_key)
        if cached is not None:
            return InterviewAnswer(
                text=cached.answer_text,
                model=cached.response_model,
                tokens_in=0,
                tokens_out=0,
                cost_usd=Decimal("0"),
                cache_hit=True,
            )
        if mode == REPLAY_ONLY:
            raise ReplayOnlyCacheMissError(
                "No cached answer exists for this interview path while CACHE_MODE=replay_only."
            )

    answer = call_provider()
    if mode == CACHE_FIRST:
        session.add(
            InterviewCacheEntry(
                cache_key=cache_key,
                persona_id=persona_id,
                model=model,
                question=question,
                prior_turn_hash=prior_turn_hash,
                answer_text=answer.text,
                response_model=answer.model,
                created_at=utcnow(),
            )
        )
        session.flush()
    return answer
