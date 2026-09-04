from __future__ import annotations

from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from conftest import API_ROOT
from src.services.interview_service import _parse_openrouter_chat_response


def _provider_payload() -> dict:
    return {
        "model": "openai/gpt-4o-mini-2024-07-18",
        "choices": [{"message": {"content": "A measured response."}}],
        "usage": {
            "prompt_tokens": 211,
            "completion_tokens": 17,
            "total_tokens": 228,
            "cost": 0.000123456789,
        },
    }


def test_openrouter_chat_response_preserves_provider_usage_exactly():
    result = _parse_openrouter_chat_response(
        _provider_payload(),
        requested_model="openai/gpt-4o-mini",
    )

    assert result.text == "A measured response."
    assert result.model == "openai/gpt-4o-mini-2024-07-18"
    assert result.tokens_in == 211
    assert result.tokens_out == 17
    assert result.cost_usd == Decimal("0.000123456789")


def test_openrouter_chat_response_accepts_measured_zero_cost_and_model_fallback():
    payload = _provider_payload()
    payload.pop("model")
    payload["usage"] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost": 0,
    }

    result = _parse_openrouter_chat_response(
        payload,
        requested_model="openai/gpt-4o-mini",
    )

    assert result.model == "openai/gpt-4o-mini"
    assert result.tokens_in == 0
    assert result.tokens_out == 0
    assert result.cost_usd == Decimal("0")


@pytest.mark.parametrize(
    ("usage", "message"),
    [
        (None, "did not include measured usage"),
        (
            {"prompt_tokens": 211, "completion_tokens": 17},
            "usage.cost is required",
        ),
        (
            {"prompt_tokens": -1, "completion_tokens": 17, "cost": 0.1},
            "usage.prompt_tokens must be a non-negative integer",
        ),
        (
            {"prompt_tokens": 211, "completion_tokens": 17, "cost": "NaN"},
            "usage.cost must be a non-negative number",
        ),
    ],
)
def test_openrouter_chat_response_rejects_unmeasured_or_invalid_usage(usage, message):
    payload = _provider_payload()
    payload["usage"] = usage

    with pytest.raises(RuntimeError, match=message):
        _parse_openrouter_chat_response(
            payload,
            requested_model="openai/gpt-4o-mini",
        )


def test_interview_turn_migration_creates_expected_schema(tmp_path):
    database_path = tmp_path / "migration.db"
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("interview_turn")}
    assert columns == {
        "id",
        "study_id",
        "persona_id",
        "session_id",
        "role",
        "text",
        "model",
        "tokens_in",
        "tokens_out",
        "cost_usd",
        "created_at",
    }
    assert {
        index["name"] for index in inspector.get_indexes("interview_turn")
    } == {"ix_interview_turn_study_session_created"}

    command.downgrade(config, "0003_fixed_personas")
    assert "interview_turn" not in inspect(engine).get_table_names()
