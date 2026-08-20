"""Guard the grounded persona path.

Persona generation silently degrades to rule-based ("heuristic") profiles when
the ACS prior tables are absent, which produces demo-shaped respondents that
still look plausible in the UI. These tests make that degradation fail loudly.

Regenerate the tables with: python scripts/build_grounding_priors.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.adapters.legacy_backend.runtime import load_module


API_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = API_ROOT / "legacy_runtime"
PRIORS_DIR = LEGACY_ROOT / "data" / "processed" / "priors"

REQUIRED_PRIORS = {
    "age_income_priors.parquet": {"age_bucket", "income_bucket", "count"},
    "ownership_home_type_priors.parquet": {"ownership_group", "home_type_group", "count"},
    "household_size_priors.parquet": {"household_size_bucket", "count"},
    "work_mode_hints.parquet": {"work_mode_hint", "count"},
}


@pytest.mark.parametrize("filename,required_columns", sorted(REQUIRED_PRIORS.items()))
def test_prior_table_present_and_shaped(filename, required_columns):
    path = PRIORS_DIR / filename
    assert path.exists(), f"Missing prior table {filename}; run scripts/build_grounding_priors.py"

    frame = pd.read_parquet(path)
    assert not frame.empty
    assert required_columns.issubset(set(frame.columns))
    assert float(frame["count"].sum()) > 0


def test_persona_generation_uses_grounded_priors():
    persona_generator = load_module("backend.simulation.persona_generator", LEGACY_ROOT)
    schemas = load_module("backend.schemas", LEGACY_ROOT)

    assert persona_generator.grounded_priors_available() is True

    profiles, mode = persona_generator.generate_persona_profiles_with_mode(
        audience_filter=schemas.AudienceFilter(age_min=30, age_max=60),
        sample_size=8,
        use_grounded_priors=True,
        seed=11,
    )
    assert mode == "grounded_priors"
    assert len(profiles) == 8


def test_grounded_personas_respect_audience_filters():
    persona_generator = load_module("backend.simulation.persona_generator", LEGACY_ROOT)
    schemas = load_module("backend.schemas", LEGACY_ROOT)

    profiles, mode = persona_generator.generate_persona_profiles_with_mode(
        audience_filter=schemas.AudienceFilter(homeowner_only=True),
        sample_size=12,
        use_grounded_priors=True,
        seed=3,
    )
    assert mode == "grounded_priors"
    assert {profile.ownership for profile in profiles} == {"owner"}


def test_household_size_shares_are_plausible():
    """Sanity-check the aggregate against published ACS household statistics."""
    frame = pd.read_parquet(PRIORS_DIR / "household_size_priors.parquet")
    shares = frame.set_index("household_size_bucket")["count"]
    total = float(shares.sum())

    # ~29% of US households are single-person; keep a wide tolerance so the test
    # tracks gross data corruption rather than year-over-year drift.
    assert 0.20 < float(shares.get("1", 0)) / total < 0.40
