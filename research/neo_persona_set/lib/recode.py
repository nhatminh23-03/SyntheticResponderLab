"""ACS PUMS recodes for the Neo Smart persona pipeline.

Bucket vocabularies deliberately match the app's
`legacy_runtime/scripts/build_grounding_features.py` so output stays schema-compatible.

One deliberate divergence: `home_type`. The app maps `BLD in (1,2) -> single_family_like` and
`BLD in (3..9) -> multifamily_like`. Verified against the official 2024 PUMS data dictionary
(https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2024.txt):

    01 Mobile home or trailer      02 One-family house detached
    03 One-family house attached   04-09 Apartments
    10 Boat, RV, van, etc.

So the app's mapping counts mobile homes as single-family and one-family attached houses as
multifamily. This module uses the correct mapping, because the outdoor-space proxy for a backyard
studio depends on telling a detached house from a mobile home or a townhouse.
"""

from __future__ import annotations

import pandas as pd

# Product constant: Tahoe Mini delivered-and-installed price.
TAHOE_MINI_PRICE = 23_000

AGE_BUCKETS = ["18_24", "25_34", "35_44", "45_54", "55_64", "65_plus"]
INCOME_BUCKETS = ["low", "middle", "upper_middle", "high"]
HOUSEHOLD_SIZE_BUCKETS = ["1", "2", "3_4", "5_plus"]
OWNERSHIP_GROUPS = ["owner", "renter", "other"]
HOME_TYPES = ["detached", "attached", "mobile", "multifamily", "boat_rv"]
WORK_MODES = ["remote_friendly", "commute_based", "not_working_or_unknown"]

# The attributes the generative models learn a joint distribution over.
MODEL_ATTRIBUTES = [
    "age_bucket",
    "income_bucket",
    "household_size_bucket",
    "ownership",
    "home_type",
    "work_mode",
]


def adjust_income(hincp: pd.Series, adjinc: pd.Series) -> pd.Series:
    """Convert HINCP to constant dollars using ADJINC (6 implied decimal places).

    Required for multi-year files: a 5-Year PUMS mixes five income years, and the 2024 5-Year
    factors range from 1.015250 to 1.222017 — up to a 22% difference if ignored.
    """
    income = pd.to_numeric(hincp, errors="coerce")
    factor = pd.to_numeric(adjinc, errors="coerce") / 1_000_000
    return income * factor


def bucket_age(series: pd.Series) -> pd.Series:
    """Bucket age, leaving under-18 as NA (they are not survey respondents)."""
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.cut(
        numeric,
        bins=[17, 24, 34, 44, 54, 64, 200],
        labels=AGE_BUCKETS,
        right=True,
    ).astype("object")


def bucket_income(series: pd.Series) -> pd.Series:
    """Map adjusted household income to the app's bucket vocabulary."""
    numeric = pd.to_numeric(series, errors="coerce")
    bucketed = pd.Series("unknown", index=series.index, dtype="object")
    bucketed.loc[numeric < 35_000] = "low"
    bucketed.loc[numeric.between(35_000, 74_999, inclusive="both")] = "middle"
    bucketed.loc[numeric.between(75_000, 149_999, inclusive="both")] = "upper_middle"
    bucketed.loc[numeric >= 150_000] = "high"
    bucketed.loc[numeric.isna()] = "unknown"
    return bucketed


def bucket_household_size(series: pd.Series) -> pd.Series:
    """Map household size to the app's bucket vocabulary."""
    numeric = pd.to_numeric(series, errors="coerce")
    bucketed = pd.Series("unknown", index=series.index, dtype="object")
    bucketed.loc[numeric == 1] = "1"
    bucketed.loc[numeric == 2] = "2"
    bucketed.loc[numeric.between(3, 4, inclusive="both")] = "3_4"
    bucketed.loc[numeric >= 5] = "5_plus"
    return bucketed


def recode_ownership(series: pd.Series) -> pd.Series:
    """TEN: 1/2 owned, 3 rented, 4 occupied without rent."""
    numeric = pd.to_numeric(series, errors="coerce")
    out = pd.Series("unknown", index=series.index, dtype="object")
    out.loc[numeric.isin([1, 2])] = "owner"
    out.loc[numeric == 3] = "renter"
    out.loc[numeric == 4] = "other"
    return out


def recode_home_type(series: pd.Series) -> pd.Series:
    """BLD -> structure type. See module docstring for why this differs from the app."""
    numeric = pd.to_numeric(series, errors="coerce")
    out = pd.Series("unknown", index=series.index, dtype="object")
    out.loc[numeric == 1] = "mobile"
    out.loc[numeric == 2] = "detached"
    out.loc[numeric == 3] = "attached"
    out.loc[numeric.between(4, 9, inclusive="both")] = "multifamily"
    out.loc[numeric == 10] = "boat_rv"
    return out


def recode_work_mode(series: pd.Series) -> pd.Series:
    """JWTRNS: 11 is 'Worked from home'; blank means not a worker."""
    numeric = pd.to_numeric(series, errors="coerce")
    out = pd.Series("not_working_or_unknown", index=series.index, dtype="object")
    out.loc[numeric == 11] = "remote_friendly"
    out.loc[numeric.notna() & (numeric != 11)] = "commute_based"
    return out


def has_outdoor_space_proxy(home_type: pd.Series) -> pd.Series:
    """Proxy for the survey's S3 screen (room for a ~117 sq ft detached structure).

    ACS has no yard variable. A detached single-family house is the defensible proxy; attached
    houses, apartments, mobile homes, and boats/RVs are treated as not qualifying. This assumption
    is recorded in the workbook's provenance sheet rather than buried here.
    """
    return home_type.eq("detached")


def price_to_income_ratio(adjusted_income: pd.Series) -> pd.Series:
    """Tahoe Mini price as a share of annual household income.

    Non-positive or missing income yields NA rather than infinity, so downstream comparisons do not
    silently treat a zero-income household as infinitely burdened.
    """
    income = pd.to_numeric(adjusted_income, errors="coerce")
    safe = income.where(income > 0)
    return TAHOE_MINI_PRICE / safe
