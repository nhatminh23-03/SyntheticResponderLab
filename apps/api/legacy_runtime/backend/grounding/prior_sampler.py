"""Prior-based grounding sampler for lightweight trait-bundle generation.

This module reads full prior tables and samples grounded trait bundles.
It does not integrate with persona generation yet.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.grounding.geography_prior_filter import apply_geography_context_to_priors
from backend.schemas import GeographyContext
from backend.schemas import AudienceFilter


_LAST_PRIOR_LOADING_NOTES: list[dict] = []


def load_grounding_priors(
    geography_context: GeographyContext | None = None,
    use_geography_filtered_priors: bool = True,
) -> dict[str, pd.DataFrame]:
    """Load grounding prior tables from processed priors directory.

    When `geography_context` is provided and geo-aware tables exist, this loader
    applies per-table geography filtering before returning priors.
    """
    global _LAST_PRIOR_LOADING_NOTES
    _LAST_PRIOR_LOADING_NOTES = []

    project_root = Path(__file__).resolve().parents[2]
    priors_dir = project_root / "data" / "processed" / "priors"

    paths = {
        "age_income": priors_dir / "age_income_priors.parquet",
        "ownership_home_type": priors_dir / "ownership_home_type_priors.parquet",
        "household_size": priors_dir / "household_size_priors.parquet",
        "work_mode": priors_dir / "work_mode_hints.parquet",
    }

    geo_paths = {
        "age_income": priors_dir / "age_income_priors_geo.parquet",
        "ownership_home_type": priors_dir / "ownership_home_type_priors_geo.parquet",
        "household_size": priors_dir / "household_size_priors_geo.parquet",
        "work_mode": priors_dir / "work_mode_hints_geo.parquet",
    }

    optional_paths = {
        "cex_affordability": priors_dir / "cex_affordability_priors.parquet",
        "cex_spending": priors_dir / "cex_spending_priors.parquet",
    }

    priors: dict[str, pd.DataFrame] = {}
    for key, path in paths.items():
        use_geo = bool(geo_paths.get(key) and geo_paths[key].exists())
        selected_path = geo_paths[key] if use_geo else path
        if not selected_path.exists():
            raise FileNotFoundError(f"Missing prior file: {selected_path}")
        priors[key] = pd.read_parquet(selected_path)
        _LAST_PRIOR_LOADING_NOTES.append(
            {
                "prior_table_name": key,
                "source_variant": "geo" if use_geo else "global",
                "source_path": str(selected_path),
            }
        )

    for key, path in optional_paths.items():
        if path.exists():
            priors[key] = pd.read_parquet(path)
            _LAST_PRIOR_LOADING_NOTES.append(
                {
                    "prior_table_name": key,
                    "source_variant": "global",
                    "source_path": str(path),
                }
            )

    if geography_context is not None and use_geography_filtered_priors:
        priors, summaries = apply_geography_context_to_priors(geography_context, priors)
        for summary in summaries:
            _LAST_PRIOR_LOADING_NOTES.append(
                {
                    "prior_table_name": summary.get("prior_table_name", ""),
                    "filter_level_used": summary.get("filter_level_used", "global"),
                    "row_count_before": int(summary.get("row_count_before", 0)),
                    "row_count_after": int(summary.get("row_count_after", 0)),
                    "narrowed": bool(summary.get("narrowed", False)),
                    "notes": str(summary.get("notes", "")),
                }
            )

    return priors


def get_last_prior_loading_notes() -> list[dict]:
    """Return per-table notes from the most recent prior loading pass."""
    return [dict(item) for item in _LAST_PRIOR_LOADING_NOTES]


def cex_affordability_priors_available(priors: dict[str, pd.DataFrame] | None = None) -> bool:
    """Return True when CEX affordability prior tables are available."""
    loaded = priors
    if loaded is None:
        try:
            loaded = load_grounding_priors()
        except Exception:
            return False

    aff = loaded.get("cex_affordability")
    spend = loaded.get("cex_spending")
    return aff is not None and spend is not None and not aff.empty and not spend.empty


def sample_grounded_traits(
    audience_filter: AudienceFilter,
    priors: dict[str, pd.DataFrame],
    seed: int | None = None,
    geography_context: GeographyContext | None = None,
    use_geography_filtered_priors: bool = True,
) -> dict[str, str]:
    """Sample a single grounded trait bundle using weighted prior sampling."""
    prepared_priors = _prepare_priors_for_sampling(
        priors=priors,
        geography_context=geography_context,
        use_geography_filtered_priors=use_geography_filtered_priors,
    )
    rng = random.Random(seed) if seed is not None else random.Random()
    return _sample_grounded_traits_with_rng(audience_filter=audience_filter, priors=prepared_priors, rng=rng)


def sample_grounded_trait_bundles(
    audience_filter: AudienceFilter,
    priors: dict[str, pd.DataFrame],
    n: int,
    seed: int | None = None,
    geography_context: GeographyContext | None = None,
    use_geography_filtered_priors: bool = True,
) -> list[dict[str, str]]:
    """Sample multiple grounded trait bundles using weighted prior sampling."""
    if n <= 0:
        return []

    prepared_priors = _prepare_priors_for_sampling(
        priors=priors,
        geography_context=geography_context,
        use_geography_filtered_priors=use_geography_filtered_priors,
    )
    rng = random.Random(seed) if seed is not None else random.Random()
    return [
        _sample_grounded_traits_with_rng(audience_filter=audience_filter, priors=prepared_priors, rng=rng)
        for _ in range(n)
    ]


def _prepare_priors_for_sampling(
    priors: dict[str, pd.DataFrame],
    geography_context: GeographyContext | None,
    use_geography_filtered_priors: bool,
) -> dict[str, pd.DataFrame]:
    """Apply optional geography filtering to caller-provided priors.

    This keeps sampling APIs geography-capable even when priors were loaded by
    external callers.
    """
    if geography_context is None or not use_geography_filtered_priors:
        return priors

    filtered, summaries = apply_geography_context_to_priors(geography_context, priors)
    if summaries:
        global _LAST_PRIOR_LOADING_NOTES
        _LAST_PRIOR_LOADING_NOTES.extend(
            {
                "prior_table_name": summary.get("prior_table_name", ""),
                "filter_level_used": summary.get("filter_level_used", "global"),
                "row_count_before": int(summary.get("row_count_before", 0)),
                "row_count_after": int(summary.get("row_count_after", 0)),
                "narrowed": bool(summary.get("narrowed", False)),
                "notes": str(summary.get("notes", "")),
            }
            for summary in summaries
        )
    return filtered


def _sample_grounded_traits_with_rng(
    audience_filter: AudienceFilter,
    priors: dict[str, pd.DataFrame],
    rng: random.Random,
) -> dict[str, str]:
    """Internal sampler using an injected RNG for deterministic bundle sequences."""
    age_income_df = priors["age_income"]
    ownership_home_df = priors["ownership_home_type"]
    household_size_df = priors["household_size"]
    work_mode_df = priors["work_mode"]

    sampled_age_income = _sample_age_income(audience_filter, age_income_df, rng)
    sampled_ownership_home = _sample_ownership_home_type(audience_filter, ownership_home_df, rng)
    sampled_household = _sample_household_size(audience_filter, household_size_df, rng)
    sampled_work_mode = _sample_work_mode(audience_filter, work_mode_df, rng)
    sampled_affordability = sample_affordability_traits(audience_filter, priors, rng=rng)

    return {
        "age_bucket": str(sampled_age_income.get("age_bucket", "unknown")),
        "income_bucket": str(sampled_age_income.get("income_bucket", "unknown")),
        "ownership_group": str(sampled_ownership_home.get("ownership_group", "unknown")),
        "home_type_group": str(sampled_ownership_home.get("home_type_group", "unknown")),
        "household_size_bucket": str(sampled_household.get("household_size_bucket", "unknown")),
        "work_mode_hint": str(sampled_work_mode.get("work_mode_hint", "not_working_or_unknown")),
        "affordability_pressure": str(sampled_affordability.get("affordability_pressure", "unknown")),
        "housing_burden_proxy": str(sampled_affordability.get("housing_burden_proxy", "unknown")),
        "spend_intensity_bucket": str(sampled_affordability.get("spend_intensity_bucket", "unknown")),
    }


def sample_affordability_traits(
    audience_filter: AudienceFilter,
    priors: dict[str, pd.DataFrame],
    seed: int | None = None,
    rng: random.Random | None = None,
) -> dict[str, str]:
    """Sample affordability traits from optional CEX priors with safe fallback."""
    local_rng = rng or (random.Random(seed) if seed is not None else random.Random())

    affordability_df = priors.get("cex_affordability")
    spending_df = priors.get("cex_spending")

    default = {
        "affordability_pressure": "unknown",
        "housing_burden_proxy": "unknown",
        "spend_intensity_bucket": "unknown",
    }

    if affordability_df is None or spending_df is None or affordability_df.empty or spending_df.empty:
        return default

    affordability_row = _sample_cex_row_with_preferences(
        audience_filter=audience_filter,
        df=affordability_df,
        prefer_pressure=True,
        rng=local_rng,
    )
    spending_row = _sample_cex_row_with_preferences(
        audience_filter=audience_filter,
        df=spending_df,
        prefer_pressure=False,
        rng=local_rng,
    )

    return {
        "affordability_pressure": str(
            affordability_row.get("affordability_pressure")
            or spending_row.get("affordability_pressure")
            or "unknown"
        ),
        "housing_burden_proxy": str(
            affordability_row.get("housing_burden_proxy")
            or spending_row.get("housing_burden_proxy")
            or "unknown"
        ),
        "spend_intensity_bucket": str(
            spending_row.get("spend_intensity_bucket")
            or affordability_row.get("spend_intensity_bucket")
            or "unknown"
        ),
    }


def _sample_cex_row_with_preferences(
    audience_filter: AudienceFilter,
    df: pd.DataFrame,
    prefer_pressure: bool,
    rng: random.Random,
) -> dict:
    """Sample one CEX prior row with lightweight audience-conditioned weighting."""
    filtered = df.copy()

    allowed_income = _allowed_income_buckets(audience_filter.income_min, audience_filter.income_max)
    if allowed_income and "income_bucket" in filtered.columns:
        constrained = filtered[filtered["income_bucket"].isin(allowed_income)]
        if not constrained.empty:
            filtered = constrained

    if audience_filter.homeowner_only and "tenure_group" in filtered.columns:
        constrained = filtered[filtered["tenure_group"] == "owner"]
        if not constrained.empty:
            filtered = constrained
    elif audience_filter.renter_only and "tenure_group" in filtered.columns:
        constrained = filtered[filtered["tenure_group"] == "renter"]
        if not constrained.empty:
            filtered = constrained

    rows = filtered.to_dict(orient="records")
    if not rows:
        rows = df.to_dict(orient="records")
    if not rows:
        return {}

    base_weights = _extract_base_weights(filtered if not filtered.empty else df)
    if len(base_weights) != len(rows):
        base_weights = [1.0] * len(rows)

    biased_weights = []
    for row, base_weight in zip(rows, base_weights):
        weight = float(base_weight)
        weight *= _audience_bias_multiplier(audience_filter, row, prefer_pressure=prefer_pressure)
        biased_weights.append(max(weight, 0.0))

    if sum(biased_weights) <= 0:
        return rows[rng.randrange(len(rows))]
    return rng.choices(rows, weights=biased_weights, k=1)[0]


def _extract_base_weights(df: pd.DataFrame) -> list[float]:
    if "share_within_source" in df.columns:
        return pd.to_numeric(df["share_within_source"], errors="coerce").fillna(0.0).tolist()
    if "share" in df.columns:
        return pd.to_numeric(df["share"], errors="coerce").fillna(0.0).tolist()
    if "count" in df.columns:
        return pd.to_numeric(df["count"], errors="coerce").fillna(0.0).tolist()
    return [1.0] * len(df)


def _audience_bias_multiplier(audience_filter: AudienceFilter, row: dict, prefer_pressure: bool) -> float:
    """Small deterministic multiplier for affordability realism by audience hints."""
    multiplier = 1.0

    pressure = str(row.get("affordability_pressure", "unknown"))
    burden = str(row.get("housing_burden_proxy", "unknown"))
    spend = str(row.get("spend_intensity_bucket", "unknown"))

    low_income_signal = bool(audience_filter.income_max is not None and audience_filter.income_max <= 75_000)
    high_income_signal = bool(audience_filter.income_min is not None and audience_filter.income_min >= 120_000)

    if low_income_signal or audience_filter.renter_only:
        if pressure == "high_pressure":
            multiplier *= 1.8 if prefer_pressure else 1.5
        if burden == "high":
            multiplier *= 1.4
        if spend == "stretched":
            multiplier *= 1.25

    if high_income_signal or audience_filter.homeowner_only:
        if pressure == "low_pressure":
            multiplier *= 1.6 if prefer_pressure else 1.4
        if burden == "low":
            multiplier *= 1.3
        if spend == "conservative":
            multiplier *= 1.2

    return multiplier


def _sample_age_income(audience_filter: AudienceFilter, df: pd.DataFrame, rng: random.Random) -> dict:
    """Sample from age-income prior table with audience filters when possible."""
    filtered = df.copy()

    allowed_age_buckets = _allowed_age_buckets(audience_filter.age_min, audience_filter.age_max)
    if allowed_age_buckets:
        filtered = filtered[filtered["age_bucket"].isin(allowed_age_buckets)]

    allowed_income_buckets = _allowed_income_buckets(audience_filter.income_min, audience_filter.income_max)
    if allowed_income_buckets:
        filtered = filtered[filtered["income_bucket"].isin(allowed_income_buckets)]

    return _weighted_row_choice(filtered if not filtered.empty else df, rng)


def _sample_ownership_home_type(audience_filter: AudienceFilter, df: pd.DataFrame, rng: random.Random) -> dict:
    """Sample ownership/home-type prior with audience filters when possible."""
    filtered = df.copy()

    if audience_filter.homeowner_only:
        filtered = filtered[filtered["ownership_group"] == "owner"]
    elif audience_filter.renter_only:
        filtered = filtered[filtered["ownership_group"] == "renter"]

    preferred_home_type_group = _preferred_home_type_group(audience_filter.home_type)
    if preferred_home_type_group is not None:
        home_filtered = filtered[filtered["home_type_group"] == preferred_home_type_group]
        if not home_filtered.empty:
            filtered = home_filtered

    if filtered.empty:
        filtered = df.copy()

    return _weighted_row_choice(filtered, rng)


def _sample_household_size(audience_filter: AudienceFilter, df: pd.DataFrame, rng: random.Random) -> dict:
    """Sample household-size prior with optional household size constraints."""
    # Household-size prior has source dimension; aggregate before sampling.
    grouped = (
        df.groupby("household_size_bucket", dropna=False)["count"]
        .sum()
        .reset_index(name="count")
    )
    total = grouped["count"].sum()
    grouped["share"] = grouped["count"] / total if total > 0 else 0.0

    filtered = grouped.copy()
    allowed_size_buckets = _allowed_household_size_buckets(
        audience_filter.household_size_min,
        audience_filter.household_size_max,
    )
    if allowed_size_buckets:
        filtered = filtered[filtered["household_size_bucket"].isin(allowed_size_buckets)]

    return _weighted_row_choice(filtered if not filtered.empty else grouped, rng)


def _sample_work_mode(audience_filter: AudienceFilter, df: pd.DataFrame, rng: random.Random) -> dict:
    """Sample work-mode prior with optional work-from-home preference."""
    working_df = df.copy()

    if audience_filter.work_from_home is True:
        # Prefer remote-friendly rows, but keep fallback path.
        remote_df = working_df[working_df["work_mode_hint"] == "remote_friendly"]
        if not remote_df.empty:
            weighted = remote_df.copy()
            if "share" in weighted.columns:
                weighted["share"] = weighted["share"] * 2.0
            return _weighted_row_choice(weighted, rng)

    if audience_filter.work_from_home is False:
        commute_df = working_df[working_df["work_mode_hint"] == "commute_based"]
        if not commute_df.empty:
            return _weighted_row_choice(commute_df, rng)

    return _weighted_row_choice(working_df, rng)


def _weighted_row_choice(df: pd.DataFrame, rng: random.Random) -> dict:
    """Pick a row using share/count weights with deterministic RNG."""
    if df.empty:
        return {}

    weights = None
    if "share" in df.columns:
        weights = pd.to_numeric(df["share"], errors="coerce").fillna(0.0).tolist()
    elif "count" in df.columns:
        weights = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).tolist()

    rows = df.to_dict(orient="records")
    if weights and sum(weights) > 0:
        return rng.choices(rows, weights=weights, k=1)[0]

    return rows[rng.randrange(len(rows))]


def _allowed_age_buckets(age_min: Optional[int], age_max: Optional[int]) -> Optional[set[str]]:
    """Map age min/max constraints to allowable age buckets."""
    if age_min is None and age_max is None:
        return None

    bucket_ranges = {
        "18_24": (18, 24),
        "25_34": (25, 34),
        "35_44": (35, 44),
        "45_54": (45, 54),
        "55_64": (55, 64),
        "65_plus": (65, 120),
        "unknown": (0, 120),
    }

    minimum = age_min if age_min is not None else 0
    maximum = age_max if age_max is not None else 120

    allowed = {
        bucket
        for bucket, (bucket_min, bucket_max) in bucket_ranges.items()
        if bucket_max >= minimum and bucket_min <= maximum
    }
    return allowed or None


def _allowed_income_buckets(income_min: Optional[int], income_max: Optional[int]) -> Optional[set[str]]:
    """Map income min/max constraints to allowable income buckets."""
    if income_min is None and income_max is None:
        return None

    bucket_ranges = {
        "low": (0, 34999),
        "middle": (35000, 74999),
        "upper_middle": (75000, 149999),
        "high": (150000, 10_000_000),
        "unknown": (0, 10_000_000),
    }

    minimum = income_min if income_min is not None else 0
    maximum = income_max if income_max is not None else 10_000_000

    allowed = {
        bucket
        for bucket, (bucket_min, bucket_max) in bucket_ranges.items()
        if bucket_max >= minimum and bucket_min <= maximum
    }
    return allowed or None


def _allowed_household_size_buckets(size_min: Optional[int], size_max: Optional[int]) -> Optional[set[str]]:
    """Map household-size min/max constraints to allowable buckets."""
    if size_min is None and size_max is None:
        return None

    bucket_ranges = {
        "1": (1, 1),
        "2": (2, 2),
        "3_4": (3, 4),
        "5_plus": (5, 20),
        "unknown": (1, 20),
    }

    minimum = size_min if size_min is not None else 1
    maximum = size_max if size_max is not None else 20

    allowed = {
        bucket
        for bucket, (bucket_min, bucket_max) in bucket_ranges.items()
        if bucket_max >= minimum and bucket_min <= maximum
    }
    return allowed or None


def _preferred_home_type_group(home_type: Optional[str]) -> Optional[str]:
    """Map audience home_type hint to normalized home_type_group target."""
    if not home_type:
        return None

    value = home_type.strip().lower()
    if any(token in value for token in ["single", "townhome", "townhouse"]):
        return "single_family_like"
    if any(token in value for token in ["condo", "apartment", "multi"]):
        return "multifamily_like"
    if any(token in value for token in ["mobile", "other"]):
        return "mobile_or_other"
    return None
