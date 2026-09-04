"""Load persona records from the interview CSV that the Census pipeline exports.

The app can otherwise only get personas from `persona_generator`. This reads one row of
`research/neo_persona_set/phase1/export_interview_csv.py` output into the same dict shape
`interview_prompt_builder.build_system_prompt` already accepts.

The bucket columns map straight across. The precise Census columns are folded into a single
`census_profile` sentence, because the bucket fields alone throw away everything that makes
these personas grounded — occupation, county, household, commute.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

BUCKET_FIELDS = (
    "persona_id",
    "age_bucket",
    "income_bucket",
    "ownership",
    "work_mode",
    "home_type",
    "fit_tier",
    "awareness_stage",
    "segment_label",
    "likely_use_case",
    "likely_barrier",
    "affordability_pressure",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _census_profile(row: dict) -> str:
    """One sentence of real Census detail, skipping anything the row leaves blank."""
    parts: list[str] = []

    age, sex = _clean(row.get("exact_age")), _clean(row.get("sex"))
    if age:
        parts.append(f"You are {age}" + (f", {sex.lower()}" if sex else ""))

    for label, key in (
        ("You live in {} County, California", "county"),
        ("Your marital status is {}", "marital_status"),
        ("Your education level is {}", "education"),
        ("You work as a {}", "occupation"),
        ("Your employment status is {}", "employment_status"),
    ):
        value = _clean(row.get(key))
        if value:
            parts.append(label.format(value))

    hours = _clean(row.get("hours_worked_per_week"))
    if hours:
        parts.append(f"You work about {hours} hours a week")

    commute, minutes = _clean(row.get("commute_mode")), _clean(row.get("commute_minutes"))
    if commute:
        parts.append(f"You get to work by {commute.lower()}" + (f", about {minutes} minutes each way" if minutes else ""))

    size, kids = _clean(row.get("household_size")), _clean(row.get("children_in_household"))
    if size:
        household = f"There are {size} people in your household"
        if kids and kids != "0":
            household += f", including {kids} child" + ("ren" if kids != "1" else "")
        parts.append(household)

    income = _clean(row.get("exact_household_income"))
    if income.isdigit():
        parts.append(f"Your household income is about ${int(income):,} a year")

    beds, built = _clean(row.get("bedrooms")), _clean(row.get("year_built"))
    if beds:
        parts.append(f"Your home has {beds} bedrooms" + (f" and was built {built}" if built else ""))

    burden = _clean(row.get("housing_cost_pct_of_income"))
    if burden:
        parts.append(f"Housing costs take about {burden}% of your income")

    return ". ".join(parts) + "." if parts else ""


def row_to_persona(row: dict) -> dict:
    """Convert one CSV row into the persona dict the prompt builder consumes."""
    persona = {field: _clean(row.get(field)) for field in BUCKET_FIELDS}

    tags = _clean(row.get("lifestyle_tags"))
    # The exporter writes tags as one cell delimited by ";" (seen live); accept | and , too.
    persona["lifestyle_tags"] = [t.strip() for t in re.split(r"[;|,]", tags) if t.strip()]

    persona["census_profile"] = _census_profile(row)

    story = " ".join(
        _clean(row.get(key))
        for key in ("headline", "biography", "daily_routine", "household_and_home", "priorities", "financial_picture", "free_time")
    ).strip()
    if story:
        persona["story"] = story

    return persona


def load_personas(csv_path: str | Path) -> list[dict]:
    """Load every persona in the file, in file order."""
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        return [row_to_persona(row) for row in csv.DictReader(handle)]


def load_persona(csv_path: str | Path, persona_id: str | None = None) -> dict:
    """Load one persona by id, or the first row when no id is given."""
    personas = load_personas(csv_path)
    if not personas:
        raise ValueError(f"No persona rows in {csv_path}")
    if persona_id is None:
        return personas[0]
    for persona in personas:
        if persona["persona_id"] == persona_id:
            return persona
    raise ValueError(f"Persona {persona_id!r} not found in {csv_path}")


def _demo() -> None:
    """Self-check: a synthetic row must survive the round trip with its detail intact."""
    row = {
        "persona_id": "P001", "age_bucket": "45-54", "income_bucket": "high",
        "ownership": "owner", "work_mode": "worked from home", "home_type": "detached single-family",
        "lifestyle_tags": "commutes by car;has children", "fit_tier": "",
        "exact_age": "47", "sex": "Female", "county": "Riverside", "occupation": "Registered Nurse",
        "household_size": "4", "children_in_household": "2", "exact_household_income": "142000",
        "bedrooms": "3", "commute_mode": "Car, truck, or van", "commute_minutes": "28",
    }
    persona = row_to_persona(row)

    assert persona["persona_id"] == "P001"
    assert persona["lifestyle_tags"] == ["commutes by car", "has children"], persona["lifestyle_tags"]
    assert persona["fit_tier"] == "", "retired columns must stay blank, never defaulted"

    profile = persona["census_profile"]
    for expected in ("47", "Riverside County", "Registered Nurse", "$142,000", "4 people", "2 children", "28 minutes"):
        assert expected in profile, f"{expected!r} missing from: {profile}"

    # A row with only bucket columns must not crash or invent detail.
    assert row_to_persona({"persona_id": "P002"})["census_profile"] == ""

    print("persona_csv self-check passed")
    print(profile)


if __name__ == "__main__":
    _demo()
