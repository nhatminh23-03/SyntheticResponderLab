"""Lightweight grounding calibration helpers.

Compares sampled persona trait proportions to grounding prior proportions.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from backend.schemas import AudienceFilter, PersonaProfile


def build_sampled_trait_dataframe(persona_profiles: Iterable[PersonaProfile]) -> pd.DataFrame:
    """Convert persona profiles into a normalized trait dataframe for calibration."""
    rows: list[dict[str, str]] = []

    for persona in persona_profiles:
        rows.append(
            {
                "age_bucket": _safe_text(persona.age_bucket),
                "income_bucket": _safe_text(persona.income_bucket),
                "ownership_group": _normalize_ownership(persona.ownership),
                "home_type_group": _normalize_home_type(persona.home_type),
                "work_mode_hint": _normalize_work_mode(persona.work_mode),
            }
        )

    return pd.DataFrame(rows)


def compare_sample_to_priors(
    persona_profiles: Iterable[PersonaProfile],
    priors: dict[str, pd.DataFrame],
    audience_filter: AudienceFilter | None = None,
) -> pd.DataFrame:
    """Build a row-wise prior vs sampled share comparison table."""
    sampled_df = build_sampled_trait_dataframe(persona_profiles)
    if sampled_df.empty:
        return pd.DataFrame(
            columns=["trait_name", "category", "prior_share", "sampled_share", "absolute_diff", "comparison_basis"]
        )

    comparisons: list[pd.DataFrame] = []

    # age_bucket prior marginal from age_income priors
    age_income_df = priors.get("age_income")
    if age_income_df is not None and {"age_bucket", "count"}.issubset(age_income_df.columns):
        age_prior = _marginal_prior_share(age_income_df, "age_bucket")
        age_prior, age_basis = _apply_trait_constraints_to_prior(age_prior, "age_bucket", audience_filter)
        age_sample = _sample_share(sampled_df, "age_bucket")
        comparisons.append(_build_trait_comparison("age_bucket", age_prior, age_sample, age_basis))

    # income_bucket prior marginal from age_income priors
    if age_income_df is not None and {"income_bucket", "count"}.issubset(age_income_df.columns):
        income_prior = _marginal_prior_share(age_income_df, "income_bucket")
        income_prior, income_basis = _apply_trait_constraints_to_prior(income_prior, "income_bucket", audience_filter)
        income_sample = _sample_share(sampled_df, "income_bucket")
        comparisons.append(_build_trait_comparison("income_bucket", income_prior, income_sample, income_basis))

    # ownership_group marginal from ownership_home_type priors
    own_home_df = priors.get("ownership_home_type")
    if own_home_df is not None and {"ownership_group", "count"}.issubset(own_home_df.columns):
        ownership_prior = _marginal_prior_share(own_home_df, "ownership_group")
        ownership_prior, ownership_basis = _apply_trait_constraints_to_prior(
            ownership_prior,
            "ownership_group",
            audience_filter,
        )
        ownership_sample = _sample_share(sampled_df, "ownership_group")
        comparisons.append(
            _build_trait_comparison("ownership_group", ownership_prior, ownership_sample, ownership_basis)
        )

    # home_type_group marginal from ownership_home_type priors
    if own_home_df is not None and {"home_type_group", "count"}.issubset(own_home_df.columns):
        home_type_prior = _marginal_prior_share(own_home_df, "home_type_group")
        home_type_prior, home_type_basis = _apply_trait_constraints_to_prior(
            home_type_prior,
            "home_type_group",
            audience_filter,
        )
        home_type_sample = _sample_share(sampled_df, "home_type_group")
        comparisons.append(
            _build_trait_comparison("home_type_group", home_type_prior, home_type_sample, home_type_basis)
        )

    # work_mode_hint from work_mode priors
    work_mode_df = priors.get("work_mode")
    if work_mode_df is not None and {"work_mode_hint", "count"}.issubset(work_mode_df.columns):
        work_mode_prior = _marginal_prior_share(work_mode_df, "work_mode_hint")
        work_mode_prior, work_mode_basis = _apply_trait_constraints_to_prior(
            work_mode_prior,
            "work_mode_hint",
            audience_filter,
        )
        work_mode_sample = _sample_share(sampled_df, "work_mode_hint")
        comparisons.append(_build_trait_comparison("work_mode_hint", work_mode_prior, work_mode_sample, work_mode_basis))

    if not comparisons:
        return pd.DataFrame(
            columns=["trait_name", "category", "prior_share", "sampled_share", "absolute_diff", "comparison_basis"]
        )

    output = pd.concat(comparisons, ignore_index=True)
    output = output.sort_values(["trait_name", "absolute_diff"], ascending=[True, False]).reset_index(drop=True)
    return output


def build_calibration_summary(
    persona_profiles: Iterable[PersonaProfile],
    priors: dict[str, pd.DataFrame],
    audience_filter: AudienceFilter | None = None,
) -> dict[str, Any]:
    """Build a lightweight summary dict from prior-vs-sampled trait comparisons."""
    comparison_df = compare_sample_to_priors(persona_profiles, priors, audience_filter=audience_filter)
    if comparison_df.empty:
        return {
            "comparison_table": comparison_df,
            "mean_absolute_diff_by_trait": {},
            "max_absolute_diff": None,
            "note": "No comparable traits found for calibration.",
            "comparison_basis_counts": {},
        }

    mean_abs_diff = (
        comparison_df.groupby("trait_name")["absolute_diff"]
        .mean()
        .sort_values(ascending=False)
        .to_dict()
    )

    max_row = comparison_df.loc[comparison_df["absolute_diff"].idxmax()]
    basis_counts = comparison_df["comparison_basis"].value_counts(dropna=False).to_dict()

    return {
        "comparison_table": comparison_df,
        "mean_absolute_diff_by_trait": mean_abs_diff,
        "comparison_basis_counts": basis_counts,
        "max_absolute_diff": {
            "trait_name": str(max_row["trait_name"]),
            "category": str(max_row["category"]),
            "absolute_diff": float(max_row["absolute_diff"]),
        },
        "note": (
            "Lightweight diagnostic comparing sampled persona traits to grounding priors. "
            "When audience constraints clearly apply, constrained expected priors are used."
        ),
    }


def _safe_text(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text if text else "unknown"


def _normalize_ownership(value: Any) -> str:
    text = _safe_text(value).lower()
    if text in {"owner", "renter", "other"}:
        return text
    return "unknown"


def _normalize_home_type(value: Any) -> str:
    text = _safe_text(value).lower()
    if any(token in text for token in ["single", "townhome", "townhouse", "house"]):
        return "single_family_like"
    if any(token in text for token in ["apartment", "condo", "multi"]):
        return "multifamily_like"
    if any(token in text for token in ["mobile", "other"]):
        return "mobile_or_other"
    if text == "unknown":
        return "unknown"
    return "unknown"


def _normalize_work_mode(value: Any) -> str:
    text = _safe_text(value).lower()
    if text == "remote":
        return "remote_friendly"
    if text == "onsite":
        return "commute_based"
    if text == "hybrid":
        return "not_working_or_unknown"
    return "not_working_or_unknown"


def _marginal_prior_share(df: pd.DataFrame, trait_col: str) -> pd.Series:
    grouped = (
        df.groupby(trait_col, dropna=False)["count"]
        .sum()
        .reset_index(name="count")
    )
    total = grouped["count"].sum()
    grouped["prior_share"] = grouped["count"] / total if total > 0 else 0.0
    grouped[trait_col] = grouped[trait_col].fillna("unknown").astype(str)
    return grouped.set_index(trait_col)["prior_share"]


def _sample_share(sampled_df: pd.DataFrame, trait_col: str) -> pd.Series:
    counts = sampled_df[trait_col].fillna("unknown").astype(str).value_counts(normalize=True)
    counts.name = "sampled_share"
    return counts


def _build_trait_comparison(
    trait_name: str,
    prior_share: pd.Series,
    sampled_share: pd.Series,
    comparison_basis: str,
) -> pd.DataFrame:
    categories = sorted(set(prior_share.index).union(set(sampled_share.index)))
    rows = []
    for category in categories:
        prior_value = float(prior_share.get(category, 0.0))
        sampled_value = float(sampled_share.get(category, 0.0))
        rows.append(
            {
                "trait_name": trait_name,
                "category": category,
                "prior_share": prior_value,
                "sampled_share": sampled_value,
                "absolute_diff": abs(prior_value - sampled_value),
                "comparison_basis": comparison_basis,
            }
        )
    return pd.DataFrame(rows)


def _apply_trait_constraints_to_prior(
    prior_share: pd.Series,
    trait_name: str,
    audience_filter: AudienceFilter | None,
) -> tuple[pd.Series, str]:
    """Apply trait-specific audience constraints to prior marginal shares.

    Returns:
        (possibly constrained prior share series, comparison basis label)
    """
    if audience_filter is None:
        return prior_share, "global_prior"

    allowed_categories: set[str] | None = None

    if trait_name == "ownership_group":
        if audience_filter.homeowner_only:
            allowed_categories = {"owner"}
        elif audience_filter.renter_only:
            allowed_categories = {"renter"}

    elif trait_name == "work_mode_hint":
        if audience_filter.work_from_home is True:
            allowed_categories = {"remote_friendly"}
        elif audience_filter.work_from_home is False:
            allowed_categories = {"commute_based"}

    elif trait_name == "age_bucket":
        allowed_categories = _allowed_age_buckets(audience_filter.age_min, audience_filter.age_max)

    elif trait_name == "income_bucket":
        allowed_categories = _allowed_income_buckets(audience_filter.income_min, audience_filter.income_max)

    elif trait_name == "home_type_group":
        preferred = _preferred_home_type_group(audience_filter.home_type)
        if preferred is not None:
            allowed_categories = {preferred}

    if not allowed_categories:
        return prior_share, "global_prior"

    constrained = prior_share[prior_share.index.isin(allowed_categories)]
    if constrained.empty:
        return prior_share, "global_prior"

    total = float(constrained.sum())
    if total <= 0:
        return prior_share, "global_prior"

    constrained = constrained / total
    return constrained, "constrained_prior"


def _allowed_age_buckets(age_min: int | None, age_max: int | None) -> set[str] | None:
    if age_min is None and age_max is None:
        return None

    ranges = {
        "18_24": (18, 24),
        "25_34": (25, 34),
        "35_44": (35, 44),
        "45_54": (45, 54),
        "55_64": (55, 64),
        "65_plus": (65, 120),
        "18-29": (18, 29),
        "30-44": (30, 44),
        "45-59": (45, 59),
        "60+": (60, 120),
        "unknown": (0, 120),
    }
    minimum = age_min if age_min is not None else 0
    maximum = age_max if age_max is not None else 120
    allowed = {
        bucket
        for bucket, (bucket_min, bucket_max) in ranges.items()
        if bucket_max >= minimum and bucket_min <= maximum
    }
    return allowed or None


def _allowed_income_buckets(income_min: int | None, income_max: int | None) -> set[str] | None:
    if income_min is None and income_max is None:
        return None

    ranges = {
        "low": (0, 34_999),
        "middle": (35_000, 74_999),
        "upper_middle": (75_000, 149_999),
        "high": (150_000, 10_000_000),
        "unknown": (0, 10_000_000),
    }
    minimum = income_min if income_min is not None else 0
    maximum = income_max if income_max is not None else 10_000_000
    allowed = {
        bucket
        for bucket, (bucket_min, bucket_max) in ranges.items()
        if bucket_max >= minimum and bucket_min <= maximum
    }
    return allowed or None


def _preferred_home_type_group(home_type: str | None) -> str | None:
    if not home_type:
        return None
    value = home_type.strip().lower()
    if any(token in value for token in ["single", "townhome", "townhouse", "house"]):
        return "single_family_like"
    if any(token in value for token in ["condo", "apartment", "multi"]):
        return "multifamily_like"
    if any(token in value for token in ["mobile", "other"]):
        return "mobile_or_other"
    return None
