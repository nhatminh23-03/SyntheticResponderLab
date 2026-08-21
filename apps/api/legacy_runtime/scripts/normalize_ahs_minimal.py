"""Normalize minimal AHS parquet file into a cleaner intermediate output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


AHS_RENAME_MAP = {
    "CONTROL": "control_id",
    "WEIGHT": "weight",
    "OMB13CBSA": "cbsa_code",
    "DIVISION": "census_division_code",
    "NUMPEOPLE": "num_people",
    "HHAGE": "householder_age",
    "HHSEX": "householder_sex",
    "HHRACE": "householder_race_code",
    "HHMAR": "householder_marital_code",
    "HHGRAD": "householder_education_code",
    "HHCITSHP": "householder_citizenship_code",
    "TENURE": "tenure_code",
    "UNITSIZE": "unit_size_code",
    "TOTROOMS": "total_rooms",
    "HEATTYPE": "heat_type_code",
    "HINCP": "household_income",
    "RENT": "rent",
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

        if len(output) > 0 and non_null >= (len(output) * 0.5):
            output[column] = coerced

    numeric_columns = output.select_dtypes(include=["number"]).columns.tolist()
    for column in numeric_columns:
        output.loc[output[column] < 0, column] = pd.NA

    return output


def main() -> None:
    """Normalize AHS minimal parquet and write metadata summary."""
    project_root = Path(__file__).resolve().parents[1]
    source_parquet = project_root / "data" / "processed" / "lookups" / "ahs_minimal.parquet"
    output_parquet = project_root / "data" / "processed" / "lookups" / "ahs_normalized.parquet"
    summary_json = project_root / "data" / "processed" / "metadata" / "ahs_normalized_summary.json"

    if not source_parquet.exists():
        raise FileNotFoundError(
            f"Missing source parquet: {source_parquet}\n"
            "Run minimal preprocessing first."
        )

    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    summary_json.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(source_parquet)
    before_columns = df.columns.tolist()
    print(f"[AHS normalized] Before columns ({len(before_columns)}): {before_columns}")

    normalized_names = {
        column: AHS_RENAME_MAP.get(column, AHS_RENAME_MAP.get(column.upper(), snake_case(column)))
        for column in before_columns
    }
    df = df.rename(columns=normalized_names)
    df = safe_numeric_coerce(df)

    after_columns = df.columns.tolist()
    print(f"[AHS normalized] After columns ({len(after_columns)}): {after_columns}")

    df.to_parquet(output_parquet, index=False)

    numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
    null_counts = {column: int(df[column].isna().sum()) for column in after_columns}

    summary: dict[str, Any] = {
        "dataset": "AHS normalized",
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
    print(f"[AHS normalized] Wrote normalized parquet: {output_parquet}")
    print(f"[AHS normalized] Wrote summary: {summary_json}")


if __name__ == "__main__":
    main()
