"""Normalize minimal CEX parquet files into cleaner intermediate outputs.

Scope:
- lightweight column normalization/cleaning only
- no persona/simulation integration
- no priors in this script
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


EXPECTED_COLUMNS = [
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

NUMERIC_COLUMNS = [
    "weight",
    "income_before_tax",
    "income_after_tax",
    "wage_income",
    "salary_income",
    "family_size",
    "rent_net",
    "housing_total",
    "shelter_total",
    "utilities_total",
    "total_expenditure",
    "food_total",
]

CODE_TEXT_COLUMNS = ["household_id", "income_rank", "tenure_code", "source_dataset", "source_file"]
NEGATIVE_TO_NULL_COLUMNS = [
    "income_before_tax",
    "income_after_tax",
    "wage_income",
    "salary_income",
    "rent_net",
    "housing_total",
    "shelter_total",
    "utilities_total",
    "total_expenditure",
    "food_total",
    "family_size",
]


def snake_case(name: str) -> str:
    """Convert arbitrary column name to snake_case."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(name).strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_").lower()


def normalize_one_dataset(
    source_path: Path,
    output_path: Path,
    summary_path: Path,
    dataset_label: str,
) -> None:
    """Normalize one CEX minimal parquet dataset and write summary."""
    if not source_path.exists():
        raise FileNotFoundError(
            f"Missing source parquet: {source_path}\n"
            "Run minimal preprocessing first: python scripts/preprocess_cex_minimal.py"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(source_path)
    before_columns = df.columns.tolist()

    # Ensure clean names and then enforce expected output schema.
    rename_map = {column: snake_case(column) for column in before_columns}
    df = df.rename(columns=rename_map)

    for column in EXPECTED_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    df = df[EXPECTED_COLUMNS].copy()

    # Numeric coercion.
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Replace negative placeholders with null where appropriate.
    for column in NEGATIVE_TO_NULL_COLUMNS:
        if column in df.columns:
            df.loc[df[column] < 0, column] = pd.NA

    # Keep code/id/source fields as text codes for now.
    for column in CODE_TEXT_COLUMNS:
        df[column] = df[column].astype("string")

    df.to_parquet(output_path, index=False)

    summary: dict[str, Any] = {
        "dataset": dataset_label,
        "source_parquet": str(source_path),
        "output_parquet": str(output_path),
        "rows": int(len(df)),
        "columns_before": before_columns,
        "columns_after": EXPECTED_COLUMNS,
        "missing_expected_columns_filled_with_null": [col for col in EXPECTED_COLUMNS if col not in rename_map.values()],
        "numeric_columns": NUMERIC_COLUMNS,
        "negative_to_null_columns": NEGATIVE_TO_NULL_COLUMNS,
        "null_counts": {column: int(df[column].isna().sum()) for column in EXPECTED_COLUMNS},
        "notes": (
            "Lightweight normalization only: snake_case names, numeric coercion, and negative placeholders to null. "
            "Code fields remain as raw codes for now."
        ),
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{dataset_label}] Wrote normalized parquet: {output_path}")
    print(f"[{dataset_label}] Wrote summary: {summary_path}")


def main() -> None:
    """Normalize CEX minimal interview and diary outputs."""
    project_root = Path(__file__).resolve().parents[1]
    lookups_dir = project_root / "data" / "processed" / "lookups"
    metadata_dir = project_root / "data" / "processed" / "metadata"

    normalize_one_dataset(
        source_path=lookups_dir / "cex_interview_minimal.parquet",
        output_path=lookups_dir / "cex_interview_normalized.parquet",
        summary_path=metadata_dir / "cex_interview_normalized_summary.json",
        dataset_label="CEX interview normalized",
    )

    normalize_one_dataset(
        source_path=lookups_dir / "cex_diary_minimal.parquet",
        output_path=lookups_dir / "cex_diary_normalized.parquet",
        summary_path=metadata_dir / "cex_diary_normalized_summary.json",
        dataset_label="CEX diary normalized",
    )


if __name__ == "__main__":
    main()
