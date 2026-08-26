"""Likely response to the Tahoe Mini, scored from ACS fields only.

Deliberately a transparent rule, not an LLM judgement: every persona's accept / unsure / reject
label has to be reproducible from its Census attributes alone, and the contributing reasons are
recorded so a reader can audit the call.

Framing note: the real survey terminates anyone without outdoor space (screener S3), so a valid
rejector is someone who PASSES screening and still declines. That makes rejection cost-driven and
value-driven rather than space-driven, which is what these rules encode.
"""

from __future__ import annotations

import pandas as pd

from lib.recode import TAHOE_MINI_PRICE

# Positive score means more likely to buy. Thresholds are stated here rather than inline so the
# workbook can print the exact rule alongside the personas.
RULES = [
    {
        "id": "price_dominates_income",
        "weight": -4.0,
        "description": f"${TAHOE_MINI_PRICE:,} exceeds 40% of annual household income",
    },
    {
        "id": "price_significant",
        "weight": -2.5,
        "description": f"${TAHOE_MINI_PRICE:,} is 20-40% of annual household income",
    },
    {
        "id": "price_noticeable",
        "weight": -1.0,
        "description": f"${TAHOE_MINI_PRICE:,} is 10-20% of annual household income",
    },
    {
        "id": "price_manageable",
        "weight": 1.5,
        "description": f"${TAHOE_MINI_PRICE:,} is under 10% of annual household income",
    },
    {
        "id": "already_cost_burdened",
        "weight": -2.0,
        "description": "Owner housing costs already exceed 30% of income (ACS OCPIP > 30)",
    },
    {
        "id": "severely_cost_burdened",
        "weight": -1.5,
        "description": "Owner housing costs exceed 50% of income (ACS OCPIP > 50)",
    },
    {
        "id": "comfortable_income",
        "weight": 2.0,
        "description": "High income bucket ($150k+), so the price is a modest share of income",
    },
    {
        "id": "upper_middle_income",
        "weight": 1.0,
        "description": "Upper-middle income bucket ($75k-$150k)",
    },
    {
        "id": "remote_work_use_case",
        "weight": 2.0,
        "description": "Works from home, so a detached office has a concrete daily use",
    },
    {
        "id": "space_pressure_household",
        "weight": 1.5,
        "description": "Household of 3+ people, so extra separated space relieves real pressure",
    },
    {
        "id": "solo_older_household",
        "weight": -1.5,
        "description": "Single-person household aged 65+, where the extra-room use case is weakest",
    },
    {
        "id": "prime_improver_age",
        "weight": 1.0,
        "description": "Householder aged 35-54, the peak home-improvement life stage",
    },
]

ACCEPT_THRESHOLD = 2.0
REJECT_THRESHOLD = -1.0


def _fired(row: pd.Series) -> list[str]:
    """Return the ids of every rule that applies to this household."""
    fired: list[str] = []

    ratio = row.get("price_to_income")
    if pd.notna(ratio):
        if ratio > 0.40:
            fired.append("price_dominates_income")
        elif ratio > 0.20:
            fired.append("price_significant")
        elif ratio > 0.10:
            fired.append("price_noticeable")
        else:
            fired.append("price_manageable")

    burden = row.get("owner_cost_burden")
    if pd.notna(burden):
        if burden > 30:
            fired.append("already_cost_burdened")
        if burden > 50:
            fired.append("severely_cost_burdened")

    if row.get("income_bucket") == "high":
        fired.append("comfortable_income")
    elif row.get("income_bucket") == "upper_middle":
        fired.append("upper_middle_income")

    if row.get("work_mode") == "remote_friendly":
        fired.append("remote_work_use_case")

    if row.get("household_size_bucket") in {"3_4", "5_plus"}:
        fired.append("space_pressure_household")

    if row.get("household_size_bucket") == "1" and row.get("age_bucket") == "65_plus":
        fired.append("solo_older_household")

    if row.get("age_bucket") in {"35_44", "45_54"}:
        fired.append("prime_improver_age")

    return fired


_WEIGHTS = {rule["id"]: rule["weight"] for rule in RULES}
_DESCRIPTIONS = {rule["id"]: rule["description"] for rule in RULES}


def score_row(row: pd.Series) -> dict:
    """Score one household and label its likely response.

    Two hard guards sit on top of the additive score, because affordability is not the kind of
    thing a lifestyle factor should be able to outweigh:

    1. A household with no measurable positive income cannot be scored at all. Without it the price
       rules never fire and the persona would drift to 'accept' by default — a silent failure that
       would put a $0-income household down as a likely buyer of a $23,000 product.
    2. If the price exceeds 30% of annual income, the best available label is 'unsure' unless the
       household is in the high-income bucket. No amount of remote-work or crowding upside makes a
       third of gross annual income an easy yes.
    """
    income = row.get("adjusted_income")
    if pd.isna(income) or income <= 0:
        return {
            "likely_response": "not_scorable",
            "response_score": float("nan"),
            "rules_fired": [],
            "reasons_for": [],
            "reasons_against": ["Household reports zero or negative annual income, so affordability cannot be assessed"],
        }

    fired = _fired(row)
    score = sum(_WEIGHTS[rule_id] for rule_id in fired)

    if score >= ACCEPT_THRESHOLD:
        response = "accept"
    elif score <= REJECT_THRESHOLD:
        response = "reject"
    else:
        response = "unsure"

    ratio = row.get("price_to_income")
    capped = False
    if response == "accept" and pd.notna(ratio) and ratio > 0.30 and row.get("income_bucket") != "high":
        response = "unsure"
        capped = True

    positives = [_DESCRIPTIONS[r] for r in fired if _WEIGHTS[r] > 0]
    negatives = [_DESCRIPTIONS[r] for r in fired if _WEIGHTS[r] < 0]
    if capped:
        negatives.append(
            f"Capped below 'accept': ${TAHOE_MINI_PRICE:,} exceeds 30% of annual income "
            "and the household is not in the high-income bracket"
        )

    return {
        "likely_response": response,
        "response_score": round(float(score), 2),
        "rules_fired": fired,
        "reasons_for": positives,
        "reasons_against": negatives,
    }


def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Score every row, returning the scoring columns aligned to the input index."""
    scored = frame.apply(score_row, axis=1, result_type="expand")
    scored.index = frame.index
    return scored
