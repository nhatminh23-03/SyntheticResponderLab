"""Build geo-aware grounding prior tables from geo-aware feature files.

This script preserves available geography keys in grouped priors where those keys
exist in inputs. It intentionally falls back to non-geo grouping when a geo key
is absent for a given table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_bool_dtype


def _grouped_prior(df: pd.DataFrame, group_cols: list[str], count_name: str = "count") -> pd.DataFrame:
    existing = [col for col in group_cols if col in df.columns]
    if not existing:
        raise RuntimeError(f"None of requested columns are present: {group_cols}")

    normalized = df[existing].copy()
    for col in existing:
        series = normalized[col]
        if is_bool_dtype(series):
            normalized[col] = series.fillna(False)
        else:
            # Keep geo keys and categorical groupers stable as strings.
            normalized[col] = series.astype("string").fillna("unknown")

    grouped = (
        normalized
        .groupby(existing, dropna=False)
        .size()
        .reset_index(name=count_name)
    )
    return grouped


def _with_shares(df: pd.DataFrame, count_col: str = "count") -> pd.DataFrame:
    total = float(df[count_col].sum()) if len(df) else 0.0
    out = df.copy()
    out["share"] = (out[count_col] / total) if total > 0 else 0.0
    return out.sort_values(count_col, ascending=False).reset_index(drop=True)


def _write_prior_and_summary(prior_df: pd.DataFrame, output_path: Path, dataset_label: str, source_paths: list[Path]) -> None:
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
        "geo_columns": [
            col for col in prior_df.columns
            if any(token in col.lower() for token in ["puma", "cbsa", "state", "county", "tract", "zip"])
        ],
        "top_rows": prior_df.head(20).to_dict(orient="records"),
        "notes": "Geo-aware prior table (best-effort, using only available geography keys).",
    }

    summary_path = metadata_dir / f"{output_path.stem}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"[{dataset_label}] Wrote prior: {output_path}")
    print(f"[{dataset_label}] Wrote summary: {summary_path}")


def _first_available(df: pd.DataFrame, candidates: list[str]) -> list[str]:
    return [col for col in candidates if col in df.columns]


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    lookups_dir = project_root / "data" / "processed" / "lookups"
    priors_dir = project_root / "data" / "processed" / "priors"

    acs_person_features_path = lookups_dir / "acs_person_features_geo.parquet"
    acs_housing_features_path = lookups_dir / "acs_housing_features_geo.parquet"
    ahs_features_path = lookups_dir / "ahs_features_geo.parquet"

    for path in [acs_person_features_path, acs_housing_features_path, ahs_features_path]:
        if not path.exists():
            raise FileNotFoundError(
                f"Missing geo feature file: {path}\n"
                "Run: PYTHONPATH=\"$(pwd)\" .venv-1/bin/python scripts/build_grounding_features_geo.py"
            )

    acs_person = pd.read_parquet(acs_person_features_path)
    acs_housing = pd.read_parquet(acs_housing_features_path)
    ahs = pd.read_parquet(ahs_features_path)

    # 1) Age-income priors (ACS person) with geo keys when available.
    age_geo = _first_available(acs_person, ["state", "puma", "cbsa_code"])
    age_income = _grouped_prior(acs_person, age_geo + ["age_bucket", "income_bucket"])
    age_income = _with_shares(age_income)
    _write_prior_and_summary(
        age_income,
        priors_dir / "age_income_priors_geo.parquet",
        "Age-income priors geo",
        [acs_person_features_path],
    )

    # 2) Ownership-home type priors (ACS housing) with geo keys when available.
    owner_geo = _first_available(acs_housing, ["state", "puma", "cbsa_code"])
    ownership_home = _grouped_prior(acs_housing, owner_geo + ["ownership_group", "home_type_group"])
    ownership_home = _with_shares(ownership_home)
    _write_prior_and_summary(
        ownership_home,
        priors_dir / "ownership_home_type_priors_geo.parquet",
        "Ownership-home-type priors geo",
        [acs_housing_features_path],
    )

    # 3) Household size priors across ACS housing + AHS, preserving source and available geo keys.
    acs_size_cols = [col for col in ["household_size_bucket", "puma", "state"] if col in acs_housing.columns]
    ahs_size_cols = [col for col in ["household_size_bucket", "cbsa_code", "state"] if col in ahs.columns]

    acs_size = acs_housing[acs_size_cols].copy() if acs_size_cols else pd.DataFrame()
    if not acs_size.empty:
        if "cbsa_code" not in acs_size.columns:
            acs_size["cbsa_code"] = "unknown"
        if "puma" not in acs_size.columns:
            acs_size["puma"] = "unknown"
        acs_size["source"] = "acs_housing"

    ahs_size = ahs[ahs_size_cols].copy() if ahs_size_cols else pd.DataFrame()
    if not ahs_size.empty:
        if "puma" not in ahs_size.columns:
            ahs_size["puma"] = "unknown"
        if "cbsa_code" not in ahs_size.columns:
            ahs_size["cbsa_code"] = "unknown"
        ahs_size["source"] = "ahs"

    household_size_source = pd.concat([acs_size, ahs_size], ignore_index=True)
    household_size = _grouped_prior(
        household_size_source,
        _first_available(household_size_source, ["state", "puma", "cbsa_code", "source", "household_size_bucket"]),
    )
    household_size = _with_shares(household_size)
    _write_prior_and_summary(
        household_size,
        priors_dir / "household_size_priors_geo.parquet",
        "Household-size priors geo",
        [acs_housing_features_path, ahs_features_path],
    )

    # 4) Work mode priors (ACS person) with geo keys when available.
    work_geo = _first_available(acs_person, ["state", "puma", "cbsa_code"])
    work_mode = _grouped_prior(acs_person, work_geo + ["work_mode_hint", "is_working"])
    work_mode = _with_shares(work_mode)
    _write_prior_and_summary(
        work_mode,
        priors_dir / "work_mode_hints_geo.parquet",
        "Work-mode-hint priors geo",
        [acs_person_features_path],
    )


if __name__ == "__main__":
    main()
