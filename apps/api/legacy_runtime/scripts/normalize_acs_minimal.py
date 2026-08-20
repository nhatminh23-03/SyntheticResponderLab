"""Normalize minimal ACS parquet files into cleaner, analysis-friendly intermediate outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ACS_PERSON_RENAME_MAP = {
    "SERIALNO": "serialno",
    "SPORDER": "person_order",
    "PUMA": "puma",
    "PWGTP": "person_weight",
    "AGEP": "age",
    "SEX": "sex_code",
    "HISP": "hispanic_code",
    "RAC1P": "race_code",
    "SCHL": "education_code",
    "MAR": "marital_status_code",
    "ESR": "employment_status_code",
    "COW": "class_of_worker_code",
    "WKHP": "hours_worked_per_week",
    "WKL": "weeks_worked_code",
    "JWTRNS": "commute_mode_code",
    "WAGP": "wage_income",
    "PINCP": "personal_income",
    "POVPIP": "poverty_ratio",
}

ACS_HOUSING_RENAME_MAP = {
    "SERIALNO": "serialno",
    "PUMA": "puma",
    "WGTP": "housing_weight",
    "TEN": "tenure_code",
    "BLD": "building_type_code",
    "RMSP": "rooms",
    "BDSP": "bedrooms",
    "NP": "num_people",
    "HHT": "household_type_code",
    "KIT": "kitchen_code",
    "PLM": "plumbing_code",
    "FS": "food_stamp_code",
    "HINCP": "household_income",
    "GRNTP": "gross_rent",
    "RNTP": "contract_rent",
    "SMOCP": "owner_monthly_cost",
    "VALP": "home_value",
    "TAXAMT": "property_tax_amount",
    "FINCP": "family_income",
}


def snake_case(name: str) -> str:
    """Convert column names to clean snake_case fallback."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_").lower()


def safe_numeric_coerce(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce columns to numeric when possible and null out negative placeholders."""
    output = df.copy()

    for column in output.columns:
        coerced = pd.to_numeric(output[column], errors="coerce")
        non_null = coerced.notna().sum()

        # Only adopt numeric conversion if at least half of values are parseable.
        if len(output) > 0 and non_null >= (len(output) * 0.5):
            output[column] = coerced

    numeric_columns = output.select_dtypes(include=["number"]).columns.tolist()
    for column in numeric_columns:
        output.loc[output[column] < 0, column] = pd.NA

    return output


def normalize_dataset(
    source_parquet: Path,
    output_parquet: Path,
    summary_json: Path,
    rename_map: dict[str, str],
    dataset_label: str,
) -> None:
    """Normalize one parquet dataset and write summary metadata."""
    if not source_parquet.exists():
        raise FileNotFoundError(
            f"Missing source parquet: {source_parquet}\n"
            "Run minimal preprocessing first."
        )

    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    summary_json.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(source_parquet)

    before_columns = df.columns.tolist()
    print(f"[{dataset_label}] Before columns ({len(before_columns)}): {before_columns}")

    normalized_names = {
        column: rename_map.get(column, rename_map.get(column.upper(), snake_case(column)))
        for column in before_columns
    }
    df = df.rename(columns=normalized_names)
    df = safe_numeric_coerce(df)

    after_columns = df.columns.tolist()
    print(f"[{dataset_label}] After columns ({len(after_columns)}): {after_columns}")

    df.to_parquet(output_parquet, index=False)

    numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
    null_counts = {column: int(df[column].isna().sum()) for column in after_columns}

    summary: dict[str, Any] = {
        "dataset": dataset_label,
        "source_parquet": str(source_parquet),
        "output_parquet": str(output_parquet),
        "rows": int(len(df)),
        "columns_before": before_columns,
        "columns_after": after_columns,
        "rename_mapping_applied": normalized_names,
        "numeric_columns": numeric_columns,
        "null_counts": null_counts,
        "notes": (
            "Lightweight normalization only: readable column names + numeric coercion + "
            "negative numeric placeholders converted to null. No category decoding or priors."
        ),
    }

    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{dataset_label}] Wrote normalized parquet: {output_parquet}")
    print(f"[{dataset_label}] Wrote summary: {summary_json}")


def main() -> None:
    """Normalize ACS person and housing minimal files."""
    project_root = Path(__file__).resolve().parents[1]
    lookups_dir = project_root / "data" / "processed" / "lookups"
    metadata_dir = project_root / "data" / "processed" / "metadata"

    normalize_dataset(
        source_parquet=lookups_dir / "acs_person_minimal.parquet",
        output_parquet=lookups_dir / "acs_person_normalized.parquet",
        summary_json=metadata_dir / "acs_person_normalized_summary.json",
        rename_map=ACS_PERSON_RENAME_MAP,
        dataset_label="ACS person normalized",
    )

    normalize_dataset(
        source_parquet=lookups_dir / "acs_housing_minimal.parquet",
        output_parquet=lookups_dir / "acs_housing_normalized.parquet",
        summary_json=metadata_dir / "acs_housing_normalized_summary.json",
        rename_map=ACS_HOUSING_RENAME_MAP,
        dataset_label="ACS housing normalized",
    )


if __name__ == "__main__":
    main()
