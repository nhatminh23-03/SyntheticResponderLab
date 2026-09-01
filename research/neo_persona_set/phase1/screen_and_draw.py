"""Phase 1, step 1 — screen the California Census data and draw personas at random.

The whole method, in order:

    California ACS records
      -> keep only households that pass THREE hard screens
      -> draw N at random from that pool
      -> attach every other Census fact about the household

There is no scoring, no points, no preference weighting, and no target-buyer tilt. Any intuition
about who the likely buyer is (younger, higher income, detached house) is context for reading the
result, never an input to the draw.

Usage:
    python phase1/select.py [--n 30] [--seed 20260825]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labels  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "out"
CACHE_DIR = OUT_DIR / "cache"

COUNTY_URL = "https://www2.census.gov/geo/docs/reference/codes2020/cou/st06_ca_cou2020.txt"
TRACT_PUMA_URL = "https://www2.census.gov/geo/docs/reference/puma2020/2020_Census_PUMA_Names_And_Codes_CA.txt"
TRACT_PUMA_FALLBACK = "https://www2.census.gov/geo/docs/reference/puma2020/2020_Census_Tract_to_2020_PUMA.txt"

# --- The three hard screens -------------------------------------------------
DETACHED_SINGLE_FAMILY = 2   # ACS BLD code 02 = "One-family house detached"
MIN_HOUSEHOLD_INCOME = 100_000
MIN_AGE = 30
MAX_AGE = 65

REFERENCE_PERSON = 20        # RELSHIPP code for the household reference person
OWNER_TENURE = (1, 2)        # TEN 1 = owned with mortgage, 2 = owned free and clear


def puma_to_county() -> dict[int, str]:
    """Map each California PUMA to the county (or counties) it covers."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    tract_cache = CACHE_DIR / "tract_to_puma_2020.txt"
    if not tract_cache.exists():
        response = requests.get(TRACT_PUMA_FALLBACK, timeout=120)
        response.raise_for_status()
        tract_cache.write_bytes(response.content)

    county_cache = CACHE_DIR / "ca_counties.txt"
    if not county_cache.exists():
        response = requests.get(COUNTY_URL, timeout=120)
        response.raise_for_status()
        county_cache.write_bytes(response.content)

    counties = pd.read_csv(county_cache, sep="|", dtype=str)
    names = {
        row["COUNTYFP"]: row["COUNTYNAME"].replace(" County", "")
        for _, row in counties.iterrows()
    }

    crosswalk = pd.read_csv(tract_cache, dtype=str, encoding="utf-8-sig")
    crosswalk.columns = [c.strip().upper() for c in crosswalk.columns]
    california = crosswalk[crosswalk["STATEFP"] == "06"].copy()
    california["county"] = california["COUNTYFP"].map(names)

    grouped = (
        california.dropna(subset=["county"])
        .groupby("PUMA5CE")["county"]
        .agg(lambda values: "/".join(sorted(set(values))[:2]))
    )
    return {int(code): name for code, name in grouped.items()}


def build_pool(owners_only: bool = False) -> tuple[pd.DataFrame, list[dict]]:
    """Join person to housing, apply the screens, and report the funnel.

    `owners_only` adds a FOURTH screen beyond the three agreed ones. It is off by default,
    because the agreed screens say nothing about tenure — a renter in a detached house passes
    all three. Turn it on for the variant that assumes the respondent can modify the property.
    """
    person = pd.read_parquet(OUT_DIR / "acs_person_slim.parquet")
    housing = pd.read_parquet(OUT_DIR / "acs_housing_slim.parquet")

    funnel: list[dict] = []

    def record(step: str, frame: pd.DataFrame) -> None:
        weighted = int(pd.to_numeric(frame["WGTP"], errors="coerce").sum()) if "WGTP" in frame else None
        funnel.append({"step": step, "records": int(len(frame)), "weighted_households": weighted})
        extra = f"   ({weighted:,} households)" if weighted else ""
        print(f"  {step:<52} {len(frame):>9,}{extra}")

    print("Screening California ACS records\n")
    record("all California housing records", housing)

    # Occupied units only; TEN is blank for vacant units and group quarters.
    occupied = housing[pd.to_numeric(housing["TEN"], errors="coerce").notna()]
    record("occupied housing units", occupied)

    # SCREEN 1 — detached single-family house.
    detached = occupied[pd.to_numeric(occupied["BLD"], errors="coerce") == DETACHED_SINGLE_FAMILY]
    record("SCREEN 1: detached single-family house", detached)

    # SCREEN 2 — household income at or above $100,000, in constant dollars.
    # HINCP must be scaled by ADJINC: the 5-year file mixes five income years, and comparing raw
    # dollars across them would put households on the wrong side of the threshold.
    detached = detached.copy()
    detached["household_income"] = (
        pd.to_numeric(detached["HINCP"], errors="coerce")
        * pd.to_numeric(detached["ADJINC"], errors="coerce")
        / 1_000_000
    )
    income_ok = detached[detached["household_income"] >= MIN_HOUSEHOLD_INCOME]
    record(f"SCREEN 2: household income >= ${MIN_HOUSEHOLD_INCOME:,}", income_ok)

    # SCREEN 3 — householder aged 30 to 65 inclusive.
    householders = person[pd.to_numeric(person["RELSHIPP"], errors="coerce") == REFERENCE_PERSON]
    joined = income_ok.merge(
        householders.drop(columns=["PUMA"]),
        on="SERIALNO",
        how="inner",
        validate="one_to_one",
    )
    record("joined to householder record", joined)

    age = pd.to_numeric(joined["AGEP"], errors="coerce")
    pool = joined[(age >= MIN_AGE) & (age <= MAX_AGE)]
    record(f"SCREEN 3: householder aged {MIN_AGE}-{MAX_AGE}", pool)

    if owners_only:
        pool = pool[pd.to_numeric(pool["TEN"], errors="coerce").isin(OWNER_TENURE)]
        record("SCREEN 4 (optional): owner-occupied", pool)

    pool = pool[pd.to_numeric(pool["WGTP"], errors="coerce") > 0]
    record("ELIGIBLE POOL", pool)

    return pool.reset_index(drop=True), funnel


def draw(pool: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Draw n households at random, without replacement.

    Selection probability is proportional to WGTP, the ACS housing-unit weight. This is what makes
    the draw random over CALIFORNIA HOUSEHOLDS rather than over ACS records: the survey deliberately
    samples some areas more heavily than others, so treating every record as equally likely would
    over-represent the oversampled groups and the result would not describe California.

    No other quantity influences selection.
    """
    rng = np.random.default_rng(seed)
    weights = pool["WGTP"].to_numpy(dtype=float)
    picks = rng.choice(len(pool), size=n, replace=False, p=weights / weights.sum())
    return pool.iloc[picks].reset_index(drop=True)


def describe(row: pd.Series, counties: dict[int, str]) -> dict:
    """Turn one Census record into a plain-language persona record.

    Every field is decoded from the household's own data. Nothing is inferred or invented, and
    race and Hispanic origin were never fetched, so neither can appear here.
    """
    def number(column):
        value = pd.to_numeric(row.get(column), errors="coerce")
        return None if pd.isna(value) else int(value)

    income = float(row["household_income"])
    age = number("AGEP")
    occupation = labels.decode("OCCP", row.get("OCCP"))
    if occupation:
        # OCCP labels are prefixed with a job-family code, e.g. "CMM-Software Developers".
        occupation = occupation.split("-", 1)[-1].strip()

    return {
        "census_id": str(row["SERIALNO"]),
        "puma": number("PUMA"),
        "county": counties.get(number("PUMA")),
        "age": age,
        "sex": labels.decode("SEX", row.get("SEX")),
        "marital_status": labels.decode("MAR", row.get("MAR")),
        "education": labels.simplify_education(labels.decode("SCHL", row.get("SCHL"))),
        "occupation": occupation,
        "employment_status": labels.decode("ESR", row.get("ESR")),
        "hours_worked_per_week": number("WKHP"),
        "commute_mode": labels.decode("JWTRNS", row.get("JWTRNS")),
        "commute_minutes": number("JWMNP"),
        "household_income": round(income),
        "household_size": number("NP"),
        "children_in_household": number("NOC"),
        "household_type": labels.decode("HHT", row.get("HHT")),
        "tenure": labels.decode("TEN", row.get("TEN")),
        "home_type": "One-family house detached",
        "bedrooms": number("BDSP"),
        "rooms": number("RMSP"),
        "year_built": labels.decode("YRBLT", row.get("YRBLT")),
        "moved_in": labels.decode("MV", row.get("MV")),
        "vehicles": labels.decode("VEH", row.get("VEH")),
        "housing_cost_pct_of_income": number("OCPIP"),
        "census_weight": number("WGTP"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=30, help="How many personas to draw.")
    parser.add_argument("--seed", type=int, default=20260825, help="Recorded so the draw is reproducible.")
    parser.add_argument("--owners-only", action="store_true", help="Add a fourth screen: owner-occupied.")
    parser.add_argument("--tag", default=None, help="Suffix for output files.")
    args = parser.parse_args()

    tag = args.tag or ("owners" if args.owners_only else "mixed")
    pool, funnel = build_pool(owners_only=args.owners_only)
    if len(pool) < args.n:
        raise SystemExit(f"Eligible pool holds only {len(pool)} records; cannot draw {args.n}.")

    print(f"\nDrawing {args.n} at random from {len(pool):,} eligible records (seed {args.seed})")
    selected = draw(pool, args.n, args.seed)

    counties = puma_to_county()
    personas = [describe(row, counties) for _, row in selected.iterrows()]
    for index, persona in enumerate(personas, start=1):
        persona["persona_id"] = f"P{index:02d}"

    payload = {
        "method": (
            "California ACS PUMS 2024 5-Year. Three hard screens (detached single-family house; "
            f"household income >= ${MIN_HOUSEHOLD_INCOME:,} in constant dollars; householder aged "
            f"{MIN_AGE}-{MAX_AGE}). Random draw from everyone who passes, with selection probability "
            "proportional to the ACS household weight so the draw is random over California "
            "households. No scoring, no preference weighting, no target-buyer adjustment."
        ),
        "screens": {
            "home_type": "ACS BLD = 02, One-family house detached",
            "income": f"HINCP x ADJINC >= {MIN_HOUSEHOLD_INCOME}",
            "age": f"householder AGEP between {MIN_AGE} and {MAX_AGE} inclusive",
            **({"tenure": "ACS TEN in (1,2), owner-occupied"} if args.owners_only else {}),
        },
        "seed": args.seed,
        "eligible_pool_records": int(len(pool)),
        "eligible_pool_households": int(pool["WGTP"].sum()),
        "drawn": args.n,
        "funnel": funnel,
        "excluded_by_design": (
            "Race and Hispanic origin were never downloaded, so they cannot influence screening, "
            "the draw, or the written stories."
        ),
        "personas": personas,
    }

    payload["variant"] = tag
    payload["owners_only"] = bool(args.owners_only)
    out_path = OUT_DIR / f"phase1_personas_{tag}.json"
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"\n{'id':<5}{'age':>4} {'sex':<7}{'county':<16}{'income':>10} {'hh':>3} {'occupation':<34}")
    print("-" * 96)
    for persona in personas:
        print(
            f"{persona['persona_id']:<5}{persona['age']:>4} {str(persona['sex'])[:6]:<7}"
            f"{str(persona['county'])[:15]:<16}${persona['household_income']:>9,}"
            f"{persona['household_size']:>3} {str(persona['occupation'])[:33]:<34}"
        )

    print(f"\nWrote {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
