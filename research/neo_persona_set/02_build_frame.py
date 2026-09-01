"""Stage 2 — build the Southern California householder frame.

Joins the person and housing PUMS extracts, restricts to Southern California PUMAs, keeps one row
per household (the reference person), and applies the recodes in lib/recode.py.

The frame deliberately keeps ALL tenures and structure types. Screening to owner + detached happens
at persona-selection time (Stage 4), for two reasons: it mirrors how the real survey works (general
panel, then the S3 screen), and filtering first would make `ownership` and `home_type` constant,
erasing exactly the joint structure the model bake-off exists to measure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import recode  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"
CACHE_DIR = HERE / "out" / "cache"

TRACT_PUMA_URL = "https://www2.census.gov/geo/docs/reference/puma2020/2020_Census_Tract_to_2020_PUMA.txt"

CA_STATE_FIPS = "06"
SOCAL_COUNTIES = {
    "037": "Los Angeles",
    "059": "Orange",
    "073": "San Diego",
    "065": "Riverside",
    "071": "San Bernardino",
    "111": "Ventura",
}

REFERENCE_PERSON = 20  # RELSHIPP code for the household reference person.


def load_socal_pumas() -> tuple[set[int], pd.DataFrame]:
    """Derive the SoCal PUMA list from the official Census tract-to-PUMA crosswalk.

    Deriving beats hardcoding: PUMA codes changed with the 2020 vintage, and a stale hardcoded list
    would silently select the wrong geography.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / "tract_to_puma_2020.txt"

    if not cached.exists():
        print(f"  fetching {TRACT_PUMA_URL}")
        response = requests.get(TRACT_PUMA_URL, timeout=120)
        response.raise_for_status()
        cached.write_bytes(response.content)
    else:
        print("  using cached tract-to-PUMA crosswalk")

    crosswalk = pd.read_csv(cached, dtype=str, encoding="utf-8-sig")
    crosswalk.columns = [c.strip().upper() for c in crosswalk.columns]

    socal = crosswalk[
        (crosswalk["STATEFP"] == CA_STATE_FIPS) & (crosswalk["COUNTYFP"].isin(SOCAL_COUNTIES))
    ].copy()
    socal["county_name"] = socal["COUNTYFP"].map(SOCAL_COUNTIES)

    # A PUMA can straddle county lines; keep one row per PUMA with the counties it touches.
    puma_map = (
        socal.groupby("PUMA5CE")["county_name"]
        .agg(lambda names: ", ".join(sorted(set(names))))
        .reset_index()
        .rename(columns={"PUMA5CE": "puma"})
    )
    puma_codes = {int(code) for code in puma_map["puma"]}
    return puma_codes, puma_map


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    provenance: dict = {"filters": []}

    def record(step: str, frame: pd.DataFrame, weight_col: str | None = None) -> None:
        entry = {"step": step, "rows": int(len(frame))}
        if weight_col and weight_col in frame.columns:
            entry["weighted_households"] = int(pd.to_numeric(frame[weight_col], errors="coerce").sum())
        provenance["filters"].append(entry)
        suffix = f" | weighted {entry['weighted_households']:,}" if "weighted_households" in entry else ""
        print(f"  {step:<44} rows {len(frame):>9,}{suffix}")

    print("[puma] resolving Southern California PUMAs")
    puma_codes, puma_map = load_socal_pumas()
    print(f"  {len(puma_codes)} distinct PUMAs across {len(SOCAL_COUNTIES)} counties")

    print("\n[load] reading PUMS extracts")
    person = pd.read_parquet(OUT_DIR / "acs_person_slim.parquet")
    housing = pd.read_parquet(OUT_DIR / "acs_housing_slim.parquet")
    record("person records (California)", person)
    record("housing records (California)", housing, "WGTP")

    print("\n[filter] building the frame")
    housing = housing[housing["PUMA"].isin(puma_codes)]
    record("housing in SoCal PUMAs", housing, "WGTP")

    # Occupied units only: TEN is blank for vacant units and group quarters.
    housing = housing[pd.to_numeric(housing["TEN"], errors="coerce").notna()]
    record("occupied housing units", housing, "WGTP")

    reference = person[pd.to_numeric(person["RELSHIPP"], errors="coerce") == REFERENCE_PERSON]
    record("person records that are householders", reference)

    frame = housing.merge(
        reference[["SERIALNO", "AGEP", "JWTRNS", "PWGTP"]],
        on="SERIALNO",
        how="inner",
        validate="one_to_one",
    )
    record("households joined to their householder", frame, "WGTP")

    # Survey respondents are adults.
    frame = frame[pd.to_numeric(frame["AGEP"], errors="coerce") >= 18]
    record("householder is 18+", frame, "WGTP")

    frame = frame[pd.to_numeric(frame["WGTP"], errors="coerce") > 0]
    record("positive housing weight", frame, "WGTP")

    print("\n[recode] deriving persona attributes")
    frame = frame.copy()
    frame["adjusted_income"] = recode.adjust_income(frame["HINCP"], frame["ADJINC"])
    frame["age_bucket"] = recode.bucket_age(frame["AGEP"])
    frame["income_bucket"] = recode.bucket_income(frame["adjusted_income"])
    frame["household_size_bucket"] = recode.bucket_household_size(frame["NP"])
    frame["ownership"] = recode.recode_ownership(frame["TEN"])
    frame["home_type"] = recode.recode_home_type(frame["BLD"])
    frame["work_mode"] = recode.recode_work_mode(frame["JWTRNS"])
    frame["has_outdoor_space"] = recode.has_outdoor_space_proxy(frame["home_type"])
    frame["price_to_income"] = recode.price_to_income_ratio(frame["adjusted_income"])
    frame["owner_cost_burden"] = pd.to_numeric(frame["OCPIP"], errors="coerce")
    frame["puma"] = frame["PUMA"].astype(int)

    # Drop rows with an unusable value in a modelled attribute; the models need complete cases.
    before = len(frame)
    complete = frame[recode.MODEL_ATTRIBUTES].notna().all(axis=1)
    for attribute in recode.MODEL_ATTRIBUTES:
        complete &= frame[attribute].ne("unknown")
    frame = frame[complete]
    record(f"complete cases on {len(recode.MODEL_ATTRIBUTES)} modelled attributes", frame, "WGTP")
    print(f"  dropped {before - len(frame):,} rows with an unknown/missing modelled attribute")

    screened = frame[frame["ownership"].eq("owner") & frame["has_outdoor_space"]]
    record("SURVEY-ELIGIBLE (owner + detached)", screened, "WGTP")

    keep = [
        "SERIALNO", "puma", "WGTP", "PWGTP",
        *recode.MODEL_ATTRIBUTES,
        "adjusted_income", "AGEP", "NP",
        "has_outdoor_space", "price_to_income", "owner_cost_burden",
    ]
    frame = frame[keep]

    out_path = OUT_DIR / "socal_frame.parquet"
    frame.to_parquet(out_path, index=False)

    provenance.update(
        {
            "source": "US Census Bureau ACS PUMS 2024 5-Year, California",
            "geography": {
                "counties": sorted(SOCAL_COUNTIES.values()),
                "puma_count": len(puma_codes),
                "puma_source": TRACT_PUMA_URL,
            },
            "unit_of_analysis": "household, represented by its reference person (RELSHIPP=20)",
            "weight": "WGTP (housing unit weight); all shares and totals are weighted",
            "income": "HINCP multiplied by ADJINC to constant dollars",
            "modelled_attributes": recode.MODEL_ATTRIBUTES,
            "assumptions": [
                "Outdoor space is proxied by a detached single-family structure (BLD=02). ACS has "
                "no yard or lot-suitability variable, so this stands in for the survey's S3 screen.",
                "The modelling frame keeps all tenures and structure types; the owner+detached "
                "screen is applied at persona selection so the joint structure stays measurable.",
                "BLD is recoded from the official 2024 PUMS dictionary, which differs from the "
                "app's build_grounding_features.py mapping (see lib/recode.py).",
            ],
            "final_rows": int(len(frame)),
            "survey_eligible_rows": int(len(screened)),
        }
    )
    (OUT_DIR / "frame_provenance.json").write_text(json.dumps(provenance, indent=2))
    puma_map.to_csv(OUT_DIR / "socal_pumas.csv", index=False)

    print(f"\nWrote {out_path.name} ({len(frame):,} rows)")
    print(f"Wrote frame_provenance.json and socal_pumas.csv ({len(puma_map)} PUMAs)")

    print("\n[distribution] weighted shares in the modelling frame")
    weights = frame["WGTP"]
    for attribute in recode.MODEL_ATTRIBUTES:
        shares = frame.groupby(attribute, observed=True).apply(
            lambda g: g["WGTP"].sum() / weights.sum(), include_groups=False
        )
        rendered = "  ".join(f"{k}={v:.1%}" for k, v in shares.sort_values(ascending=False).items())
        print(f"  {attribute:<24} {rendered}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
