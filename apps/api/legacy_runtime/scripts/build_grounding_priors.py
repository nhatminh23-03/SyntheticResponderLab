"""Build simple grounding prior tables from derived ACS/AHS feature files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def with_shares(df: pd.DataFrame, count_col: str = "count") -> pd.DataFrame:
    """Add overall share and return sorted by count desc."""
    total = float(df[count_col].sum()) if len(df) else 0.0
    output = df.copy()
    output["share"] = (output[count_col] / total) if total > 0 else 0.0
    return output.sort_values(count_col, ascending=False).reset_index(drop=True)


def grouped_prior(df: pd.DataFrame, group_cols: list[str], count_name: str = "count") -> pd.DataFrame:
    """Build a count table from group columns with safe handling."""
    existing = [col for col in group_cols if col in df.columns]
    if not existing:
        raise RuntimeError(f"None of the requested group columns exist: {group_cols}")

    grouped = (
        df[existing]
        .fillna("unknown")
        .groupby(existing, dropna=False)
        .size()
        .reset_index(name=count_name)
    )
    return grouped


def write_prior_and_summary(
    prior_df: pd.DataFrame,
    output_path: Path,
    dataset_label: str,
    source_paths: list[Path],
) -> None:
    """Write prior parquet and metadata summary JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_dir = output_path.parents[1] / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    prior_df.to_parquet(output_path, index=False)

    summary: dict[str, Any] = {
        "dataset": dataset_label,
        "source_paths": [str(path) for path in source_paths],
        "output_path": str(output_path),
        "rows": int(len(prior_df)),
        "columns": prior_df.columns.tolist(),
        "top_rows": prior_df.head(20).to_dict(orient="records"),
        "notes": "Simple count/share prior table for future grounding integration.",
    }

    summary_path = metadata_dir / f"{output_path.stem}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"[{dataset_label}] Wrote prior: {output_path}")
    print(f"[{dataset_label}] Wrote summary: {summary_path}")


def main() -> None:
    """Build first-pass grounding priors from feature files."""
    project_root = Path(__file__).resolve().parents[1]
    lookups_dir = project_root / "data" / "processed" / "lookups"
    priors_dir = project_root / "data" / "processed" / "priors"

    acs_person_features_path = lookups_dir / "acs_person_features.parquet"
    acs_housing_features_path = lookups_dir / "acs_housing_features.parquet"
    ahs_features_path = lookups_dir / "ahs_features.parquet"

    for path in [acs_person_features_path, acs_housing_features_path, ahs_features_path]:
        if not path.exists():
            raise FileNotFoundError(
                f"Missing feature file: {path}\n"
                "Run: python scripts/build_grounding_features.py"
            )

    acs_person = pd.read_parquet(acs_person_features_path)
    acs_housing = pd.read_parquet(acs_housing_features_path)
    ahs = pd.read_parquet(ahs_features_path)

    # 1) Age-income priors from ACS person features.
    age_income = grouped_prior(acs_person, ["age_bucket", "income_bucket"])
    age_income = with_shares(age_income)
    write_prior_and_summary(
        age_income,
        priors_dir / "age_income_priors.parquet",
        "Age-income priors",
        [acs_person_features_path],
    )

    # 2) Ownership-home type priors from ACS housing.
    ownership_home = grouped_prior(acs_housing, ["ownership_group", "home_type_group"])
    ownership_home = with_shares(ownership_home)
    write_prior_and_summary(
        ownership_home,
        priors_dir / "ownership_home_type_priors.parquet",
        "Ownership-home-type priors",
        [acs_housing_features_path],
    )

    # 3) Household size priors from ACS housing + AHS.
    acs_size = acs_housing[["household_size_bucket"]].copy() if "household_size_bucket" in acs_housing.columns else pd.DataFrame()
    if not acs_size.empty:
        acs_size["source"] = "acs_housing"

    ahs_size = ahs[["household_size_bucket"]].copy() if "household_size_bucket" in ahs.columns else pd.DataFrame()
    if not ahs_size.empty:
        ahs_size["source"] = "ahs"

    household_size_source = pd.concat([acs_size, ahs_size], ignore_index=True) if not (acs_size.empty and ahs_size.empty) else pd.DataFrame(columns=["household_size_bucket", "source"])
    household_size = grouped_prior(household_size_source, ["source", "household_size_bucket"])
    household_size = with_shares(household_size)
    write_prior_and_summary(
        household_size,
        priors_dir / "household_size_priors.parquet",
        "Household-size priors",
        [acs_housing_features_path, ahs_features_path],
    )

    # 4) Work mode hint priors from ACS person.
    work_mode = grouped_prior(acs_person, ["work_mode_hint", "is_working"])
    work_mode = with_shares(work_mode)
    write_prior_and_summary(
        work_mode,
        priors_dir / "work_mode_hints.parquet",
        "Work-mode-hint priors",
        [acs_person_features_path],
    )


if __name__ == "__main__":
    main()
