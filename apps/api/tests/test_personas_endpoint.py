from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.persistence.models import Persona
from src.persistence.persona_seed import EXPECTED_PERSONA_COUNT, load_persona_seed_rows


def test_persona_seed_contains_the_30_fixed_profiles():
    seed_rows = load_persona_seed_rows()

    assert len(seed_rows) == EXPECTED_PERSONA_COUNT
    assert [row["persona_id"] for row in seed_rows] == [
        f"P{index:03d}" for index in range(1, EXPECTED_PERSONA_COUNT + 1)
    ]
    assert all(row["profile_json"]["fit_tier"] == "" for row in seed_rows)
    assert seed_rows[0]["profile_json"]["lifestyle_tags"] == [
        "lives alone",
        "commutes daily",
        "long commute",
        "works long hours",
        "multiple vehicles",
        "older home",
    ]
    assert "about $104,999 a year" in seed_rows[0]["profile_json"]["census_profile"]
    assert "including 1 child" in seed_rows[3]["profile_json"]["census_profile"]
    assert "minutes each way" not in seed_rows[1]["profile_json"]["census_profile"]


def test_persona_seed_rejects_an_incomplete_file(tmp_path):
    seed_path = tmp_path / "personas-B.csv"
    seed_path.write_text("persona_id\nage-one\n", encoding="utf-8")

    try:
        load_persona_seed_rows(seed_path)
    except ValueError as exc:
        assert "exactly 30 rows" in str(exc)
    else:
        raise AssertionError("An incomplete persona seed must be rejected.")


def test_persona_seed_rejects_duplicate_ids(tmp_path):
    seed_path = tmp_path / "personas-B.csv"
    duplicate_rows = "".join("duplicate\n" for _ in range(EXPECTED_PERSONA_COUNT))
    seed_path.write_text(f"persona_id\n{duplicate_rows}", encoding="utf-8")

    try:
        load_persona_seed_rows(seed_path)
    except ValueError as exc:
        assert "unique, non-empty persona_id" in str(exc)
    else:
        raise AssertionError("Duplicate persona ids must be rejected.")


def test_personas_endpoint_serves_database_rows_in_seed_order(client, db_session):
    seed_rows = load_persona_seed_rows()
    seed_rows[0]["profile_json"] = {
        **seed_rows[0]["profile_json"],
        "headline": "database-only sentinel",
    }
    db_session.add_all(Persona(**row) for row in reversed(seed_rows))
    db_session.commit()

    response = client.get("/api/v1/personas")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source"] == "database"
    assert len(payload["personas"]) == EXPECTED_PERSONA_COUNT
    assert [persona["persona_id"] for persona in payload["personas"]] == [
        f"P{index:03d}" for index in range(1, EXPECTED_PERSONA_COUNT + 1)
    ]
    assert payload["personas"][0] == seed_rows[0]["profile_json"]


def test_alembic_migration_seeds_personas(tmp_path):
    api_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "migration.db"
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        personas = session.scalars(select(Persona).order_by(Persona.row_index)).all()

    assert len(personas) == EXPECTED_PERSONA_COUNT
    assert personas[0].persona_id == "P001"
    assert personas[-1].persona_id == "P030"
