"""Build first-pass CEX affordability features and priors.

Scope:
- derive simple affordability features from normalized CEX outputs
- write feature parquet files + grouped prior tables (count/share)
- no persona/simulation integration in this step
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


CORE_COLUMNS = [
    "household_id",
    "weight",
    "income_before_tax",
    "income_after_tax",
    "wage_income",
    "salary_income",
    "income_rank",
    "family_size",
    "tenure_code",
    "rent_net",
    "housing_total",
    "shelter_total",
    "utilities_total",
    "total_expenditure",
    "food_total",
    "source_dataset",
    "source_file",
]


def bucket_income(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    out = pd.Series("unknown", index=series.index, dtype="string")
    out.loc[numeric.between(0, 34_999, inclusive="both")] = "low"
    out.loc[numeric.between(35_000, 74_999, inclusive="both")] = "middle"
    out.loc[numeric.between(75_000, 149_999, inclusive="both")] = "upper_middle"
    out.loc[numeric >= 150_000] = "high"
    return out


def bucket_family_size(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    out = pd.Series("unknown", index=series.index, dtype="string")
    out.loc[numeric == 1] = "1"
    out.loc[numeric == 2] = "2"
    out.loc[numeric.between(3, 4, inclusive="both")] = "3_4"
    out.loc[numeric >= 5] = "5_plus"
    return out


def map_tenure_group(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.lower()
    numeric = pd.to_numeric(series, errors="coerce")

    out = pd.Series("unknown", index=series.index, dtype="string")

    # Simple readable mapping; keep conservative semantics.
    out.loc[numeric.isin([1, 2])] = "owner"
    out.loc[numeric.isin([3, 4])] = "renter"
    out.loc[numeric.notna() & ~numeric.isin([1, 2, 3, 4])] = "other"

    # Text fallback if numeric mapping unavailable.
    out.loc[text.str.contains("own", na=False)] = "owner"
    out.loc[text.str.contains("rent", na=False)] = "renter"

    return out


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    out = pd.Series(pd.NA, index=numerator.index, dtype="Float64")
    valid = den > 0
    out.loc[valid] = num.loc[valid] / den.loc[valid]
    return out


def bucket_housing_burden(ratio: pd.Series) -> pd.Series:
    out = pd.Series("unknown", index=ratio.index, dtype="string")
    out.loc[ratio.notna() & (ratio <= 0.20)] = "low"
    out.loc[ratio.notna() & (ratio > 0.20) & (ratio <= 0.35)] = "moderate"
    out.loc[ratio.notna() & (ratio > 0.35)] = "high"
    return out


def bucket_spend_intensity(ratio: pd.Series) -> pd.Series:
    out = pd.Series("unknown", index=ratio.index, dtype="string")
    out.loc[ratio.notna() & (ratio <= 0.80)] = "conservative"
    out.loc[ratio.notna() & (ratio > 0.80) & (ratio <= 1.10)] = "balanced"
    out.loc[ratio.notna() & (ratio > 1.10)] = "stretched"
    return out


def derive_affordability_pressure(
    housing_burden_proxy: pd.Series,
    spend_intensity_bucket: pd.Series,
) -> pd.Series:
    out = pd.Series("unknown", index=housing_burden_proxy.index, dtype="string")

    high_mask = (housing_burden_proxy == "high") | (spend_intensity_bucket == "stretched")
    moderate_mask = (housing_burden_proxy == "moderate") | (spend_intensity_bucket == "balanced")
    low_mask = (housing_burden_proxy == "low") & (spend_intensity_bucket == "conservative")

    out.loc[high_mask] = "high_pressure"
    out.loc[moderate_mask & ~high_mask] = "moderate_pressure"
    out.loc[low_mask & ~(high_mask | moderate_mask)] = "low_pressure"

    return out


def add_shares(df: pd.DataFrame, count_col: str = "count") -> pd.DataFrame:
    output = df.copy()
    total = float(output[count_col].sum()) if len(output) else 0.0
    output["share"] = (output[count_col] / total) if total > 0 else 0.0

    if "source_dataset" in output.columns:
        source_total = output.groupby("source_dataset")[count_col].transform("sum")
        output["share_within_source"] = output[count_col] / source_total.where(source_total > 0, pd.NA)
        output["share_within_source"] = output["share_within_source"].fillna(0.0)

    return output.sort_values(count_col, ascending=False).reset_index(drop=True)


def grouped_prior(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    existing = [col for col in group_cols if col in df.columns]
    if not existing:
        raise RuntimeError(f"No grouping columns available from requested set: {group_cols}")

    grouped = (
        df[existing]
        .fillna("unknown")
        .groupby(existing, dropna=False)
        .size()
        .reset_index(name="count")
    )
    return grouped


def ensure_core_columns(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for col in CORE_COLUMNS:
        if col not in output.columns:
            output[col] = pd.NA
    return output[CORE_COLUMNS]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = ensure_core_columns(df)

    income_value = pd.to_numeric(out["income_after_tax"], errors="coerce")
    income_value = income_value.where(income_value.notna(), pd.to_numeric(out["income_before_tax"], errors="coerce"))

    wage_plus_salary = pd.to_numeric(out["wage_income"], errors="coerce").fillna(0) + pd.to_numeric(out["salary_income"], errors="coerce").fillna(0)
    income_value = income_value.where(income_value.notna(), wage_plus_salary)

    housing_cost_value = pd.to_numeric(out["housing_total"], errors="coerce")
    housing_cost_value = housing_cost_value.where(housing_cost_value.notna(), pd.to_numeric(out["rent_net"], errors="coerce"))

    spend_value = pd.to_numeric(out["total_expenditure"], errors="coerce")

    housing_burden_ratio = _safe_ratio(housing_cost_value, income_value)
    spend_intensity_ratio = _safe_ratio(spend_value, income_value)

    out["income_bucket"] = bucket_income(income_value)
    out["family_size_bucket"] = bucket_family_size(out["family_size"])
    out["tenure_group"] = map_tenure_group(out["tenure_code"])
    out["housing_burden_proxy"] = bucket_housing_burden(housing_burden_ratio)
    out["spend_intensity_bucket"] = bucket_spend_intensity(spend_intensity_ratio)
    out["affordability_pressure"] = derive_affordability_pressure(
        housing_burden_proxy=out["housing_burden_proxy"],
        spend_intensity_bucket=out["spend_intensity_bucket"],
    )

    return out


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    lookups_dir = project_root / "data" / "processed" / "lookups"
    priors_dir = project_root / "data" / "processed" / "priors"
    metadata_dir = project_root / "data" / "processed" / "metadata"

    interview_norm = lookups_dir / "cex_interview_normalized.parquet"
    diary_norm = lookups_dir / "cex_diary_normalized.parquet"

    for path in [interview_norm, diary_norm]:
        if not path.exists():
            raise FileNotFoundError(
                f"Missing normalized CEX input: {path}\n"
                "Run: python scripts/normalize_cex_minimal.py"
            )

    priors_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    interview_df = pd.read_parquet(interview_norm)
    diary_df = pd.read_parquet(diary_norm)

    interview_features = build_features(interview_df)
    diary_features = build_features(diary_df)

    interview_features_path = lookups_dir / "cex_interview_features.parquet"
    diary_features_path = lookups_dir / "cex_diary_features.parquet"

    interview_features.to_parquet(interview_features_path, index=False)
    diary_features.to_parquet(diary_features_path, index=False)

    all_features = pd.concat([interview_features, diary_features], ignore_index=True)

    affordability_prior = grouped_prior(
        all_features,
        [
            "source_dataset",
            "income_bucket",
            "family_size_bucket",
            "tenure_group",
            "housing_burden_proxy",
            "affordability_pressure",
        ],
    )
    affordability_prior = add_shares(affordability_prior)

    spending_prior = grouped_prior(
        all_features,
        [
            "source_dataset",
            "income_bucket",
            "spend_intensity_bucket",
            "housing_burden_proxy",
            "affordability_pressure",
        ],
    )
    spending_prior = add_shares(spending_prior)

    affordability_prior_path = priors_dir / "cex_affordability_priors.parquet"
    spending_prior_path = priors_dir / "cex_spending_priors.parquet"

    affordability_prior.to_parquet(affordability_prior_path, index=False)
    spending_prior.to_parquet(spending_prior_path, index=False)

    write_summary(
        metadata_dir / "cex_affordability_priors_summary.json",
        {
            "dataset": "CEX affordability priors",
            "source_feature_files": [str(interview_features_path), str(diary_features_path)],
            "output_prior_file": str(affordability_prior_path),
            "rows": int(len(affordability_prior)),
            "columns": affordability_prior.columns.tolist(),
            "top_rows": affordability_prior.head(30).to_dict(orient="records"),
            "notes": "First-pass grouped affordability priors (count/share) from normalized CEX features.",
        },
    )

    write_summary(
        metadata_dir / "cex_spending_priors_summary.json",
        {
            "dataset": "CEX spending priors",
            "source_feature_files": [str(interview_features_path), str(diary_features_path)],
            "output_prior_file": str(spending_prior_path),
            "rows": int(len(spending_prior)),
            "columns": spending_prior.columns.tolist(),
            "top_rows": spending_prior.head(30).to_dict(orient="records"),
            "notes": "First-pass grouped spending priors (count/share) from normalized CEX features.",
        },
    )

    print(f"Wrote feature files: {interview_features_path}, {diary_features_path}")
    print(f"Wrote prior files: {affordability_prior_path}, {spending_prior_path}")


if __name__ == "__main__":
    main()
