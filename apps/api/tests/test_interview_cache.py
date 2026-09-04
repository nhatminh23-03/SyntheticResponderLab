from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select

from conftest import API_ROOT
from src.persistence.models import InterviewCacheEntry
from src.services.interview_cache import (
    InterviewAnswer,
    ReplayOnlyCacheMissError,
    build_interview_cache_key,
    hash_prior_turns,
    resolve_interview_answer,
)


def _answer(text: str = "A live answer.") -> InterviewAnswer:
    return InterviewAnswer(
        text=text,
        model="provider/model-version",
        tokens_in=120,
        tokens_out=18,
        cost_usd=Decimal("0.00042"),
    )


def test_cache_key_is_stable_and_includes_every_required_input():
    prior_turns = [
        {"role": "user", "content": "What matters most?"},
        {"role": "assistant", "content": "A predictable installation."},
    ]
    prior_turn_hash = hash_prior_turns(prior_turns)
    inputs = {
        "persona_id": "neo-001",
        "model": "openai/gpt-4o-mini",
        "question": "What would build confidence?",
        "prior_turn_hash": prior_turn_hash,
    }
    expected = build_interview_cache_key(**inputs)

    assert len(prior_turn_hash) == 64
    assert len(expected) == 64
    assert build_interview_cache_key(**inputs) == expected
    assert hash_prior_turns(list(reversed(prior_turns))) != prior_turn_hash
    for field, replacement in {
        "persona_id": "neo-002",
        "model": "anthropic/claude-haiku",
        "question": "What would slow you down?",
        "prior_turn_hash": hash_prior_turns([]),
    }.items():
        changed = {**inputs, field: replacement}
        assert build_interview_cache_key(**changed) != expected


def test_cache_first_calls_provider_once_then_replays_at_zero_cost(db_session):
    provider_calls = 0

    def call_provider() -> InterviewAnswer:
        nonlocal provider_calls
        provider_calls += 1
        return _answer()

    kwargs = {
        "persona_id": "neo-001",
        "model": "requested/model",
        "question": "What would build confidence?",
        "prior_turns": [{"role": "assistant", "content": "Earlier answer."}],
        "call_provider": call_provider,
    }
    live = resolve_interview_answer(db_session, cache_mode="cache_first", **kwargs)
    cached = resolve_interview_answer(db_session, cache_mode="cache_first", **kwargs)
    replayed = resolve_interview_answer(db_session, cache_mode="replay_only", **kwargs)

    assert provider_calls == 1
    assert live.cache_hit is False
    assert live.cost_usd == Decimal("0.00042")
    assert cached == replayed
    assert cached.cache_hit is True
    assert (cached.tokens_in, cached.tokens_out, cached.cost_usd) == (0, 0, Decimal("0"))
    assert cached.text == live.text
    assert cached.model == "provider/model-version"
    entries = db_session.scalars(select(InterviewCacheEntry)).all()
    assert len(entries) == 1
    assert entries[0].model == "requested/model"


def test_postgres_cache_resolution_locks_key_before_lookup():
    calls = []
    cached_entry = SimpleNamespace(
        answer_text="A cached answer.",
        response_model="provider/model-version",
    )

    class RecordingSession:
        def get_bind(self):
            calls.append("get_bind")
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

        def get(self, model, cache_key):
            calls.append(("get", model, cache_key))
            return cached_entry

    def fail_if_called() -> InterviewAnswer:
        raise AssertionError("a locked cache hit must not call the provider")

    answer = resolve_interview_answer(
        RecordingSession(),
        cache_mode="cache_first",
        persona_id="neo-001",
        model="requested/model",
        question="What would build confidence?",
        prior_turns=[],
        call_provider=fail_if_called,
    )

    assert calls[0] == "get_bind"
    assert calls[1][0] == "SELECT pg_advisory_xact_lock(:lock_id)"
    assert isinstance(calls[1][1]["lock_id"], int)
    assert calls[2][0] == "get"
    assert answer.cache_hit is True


def test_replay_only_miss_never_calls_provider(db_session):
    def fail_if_called() -> InterviewAnswer:
        raise AssertionError("replay_only must not call the provider")

    with pytest.raises(ReplayOnlyCacheMissError, match="CACHE_MODE=replay_only"):
        resolve_interview_answer(
            db_session,
            cache_mode="replay_only",
            persona_id="neo-001",
            model="requested/model",
            question="A new question",
            prior_turns=[],
            call_provider=fail_if_called,
        )


def test_off_always_calls_provider_and_does_not_populate_cache(db_session):
    provider_calls = 0

    def call_provider() -> InterviewAnswer:
        nonlocal provider_calls
        provider_calls += 1
        return _answer(f"Live answer {provider_calls}.")

    kwargs = {
        "cache_mode": "off",
        "persona_id": "neo-001",
        "model": "requested/model",
        "question": "Repeat me",
        "prior_turns": [],
        "call_provider": call_provider,
    }
    first = resolve_interview_answer(db_session, **kwargs)
    second = resolve_interview_answer(db_session, **kwargs)

    assert provider_calls == 2
    assert first.text == "Live answer 1."
    assert second.text == "Live answer 2."
    assert first.cache_hit is second.cache_hit is False
    assert db_session.scalars(select(InterviewCacheEntry)).all() == []


def test_interview_cache_migration_creates_expected_schema(tmp_path):
    database_path = tmp_path / "migration.db"
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("interview_cache")} == {
        "cache_key",
        "persona_id",
        "model",
        "question",
        "prior_turn_hash",
        "answer_text",
        "response_model",
        "created_at",
    }

    command.downgrade(config, "0004_interview_turn")
    assert "interview_cache" not in inspect(engine).get_table_names()
