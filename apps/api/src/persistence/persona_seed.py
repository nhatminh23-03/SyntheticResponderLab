from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional


PERSONA_SEED_PATH = Path(__file__).resolve().parents[2] / "seed_data" / "personas-B.csv"
EXPECTED_PERSONA_COUNT = 30


def _census_profile(row: Dict[str, str]) -> str:
    parts: List[str] = []

    exact_age = row.get("exact_age", "").strip()
    sex = row.get("sex", "").strip()
    if exact_age:
        parts.append(f"You are {exact_age}{f', {sex.lower()}' if sex else ''}")

    county = row.get("county", "").strip()
    if county:
        parts.append(f"You live in {county} County, California")

    direct_fields = (
        ("marital_status", "Your marital status is {}"),
        ("education", "Your education level is {}"),
        ("occupation", "You work as a {}"),
        ("hours_worked_per_week", "You work about {} hours a week"),
    )
    for key, template in direct_fields:
        value = row.get(key, "").strip()
        if value:
            parts.append(template.format(value))

    commute_mode = row.get("commute_mode", "").strip()
    commute_minutes = row.get("commute_minutes", "").strip()
    if commute_mode:
        commute_detail = f", about {commute_minutes} minutes each way" if commute_minutes else ""
        parts.append(f"You get to work by {commute_mode.lower()}{commute_detail}")

    household_size = row.get("household_size", "").strip()
    children = row.get("children_in_household", "").strip()
    if household_size:
        children_detail = ""
        if children and children != "0":
            children_detail = f", including {children} child{'ren' if children != '1' else ''}"
        parts.append(f"There are {household_size} people in your household{children_detail}")

    income = row.get("exact_household_income", "").strip()
    if income.isdigit():
        parts.append(f"Your household income is about ${int(income):,} a year")

    bedrooms = row.get("bedrooms", "").strip()
    year_built = row.get("year_built", "").strip()
    if bedrooms and bedrooms != "0":
        year_detail = f" and was built {year_built}" if year_built else ""
        parts.append(f"Your home has {bedrooms} bedrooms{year_detail}")
    elif year_built:
        parts.append(f"Your home was built {year_built}")

    housing_cost = row.get("housing_cost_pct_of_income", "").strip()
    if housing_cost:
        parts.append(f"Housing costs take about {housing_cost}% of your income")

    return f"{'. '.join(parts)}." if parts else ""


def _persona_profile(row: Dict[str, str]) -> dict:
    return {
        "persona_id": row.get("persona_id", "").strip(),
        "age_bucket": row.get("age_bucket", "").strip(),
        "income_bucket": row.get("income_bucket", "").strip(),
        "ownership": row.get("ownership", "").strip(),
        "home_type": row.get("home_type", "").strip(),
        "work_mode": row.get("work_mode", "").strip(),
        "fit_tier": row.get("fit_tier", "").strip(),
        "lifestyle_tags": [
            value.strip()
            for value in row.get("lifestyle_tags", "").split(";")
            if value.strip()
        ],
        "census_profile": _census_profile(row),
        "headline": row.get("headline", "").strip(),
    }


def load_persona_seed_rows(path: Optional[Path] = None) -> List[dict]:
    seed_path = path or PERSONA_SEED_PATH
    with seed_path.open(newline="", encoding="utf-8-sig") as handle:
        profiles = [_persona_profile(row) for row in csv.DictReader(handle)]

    if len(profiles) != EXPECTED_PERSONA_COUNT:
        raise ValueError(
            f"Persona seed must contain exactly {EXPECTED_PERSONA_COUNT} rows; found {len(profiles)}."
        )

    persona_ids = [profile["persona_id"] for profile in profiles]
    if any(not persona_id for persona_id in persona_ids) or len(set(persona_ids)) != len(persona_ids):
        raise ValueError("Persona seed must contain a unique, non-empty persona_id for every row.")

    return [
        {
            "persona_id": profile["persona_id"],
            "row_index": index,
            "profile_json": profile,
        }
        for index, profile in enumerate(profiles)
    ]
