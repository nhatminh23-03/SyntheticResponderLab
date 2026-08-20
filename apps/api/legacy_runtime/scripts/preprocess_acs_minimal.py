"""Minimal ACS preprocessing: keep candidate grounding columns and write compact parquet outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


CHUNK_SIZE = 200_000

ACS_PERSON_CANDIDATE_COLUMNS = [
    # Linkage / geography / weights
    "SERIALNO",
    "SPORDER",
    "ST",
    "PUMA",
    "PWGTP",
    # Person grounding basics
    "AGEP",
    "SEX",
    "HISP",
    "RAC1P",
    "SCHL",
    "MAR",
    "RELP",
    # Work / status
    "ESR",
    "COW",
    "WKHP",
    "WKL",
    "JWTRNS",
    # Income / affordability
    "WAGP",
    "PINCP",
    "POVPIP",
    # Household context exposed in person file
    "NP",
    "NOC",
]

ACS_HOUSING_CANDIDATE_COLUMNS = [
    # Linkage / geography / weights
    "SERIALNO",
    "ST",
    "PUMA",
    "WGTP",
    # Tenure / occupancy
    "TEN",
    "TYPE",
    "BLD",
    "YBL",
    # Home characteristics
    "RMSP",
    "BDSP",
    "NP",
    "HHT",
    "ACCESS",
    "KIT",
    "PLM",
    "FS",
    # Cost / income / financial context
    "HINCP",
    "GRNTP",
    "RNTP",
    "SMOCP",
    "VALP",
    "TAXAMT",
    "FINCP",
]


def choose_existing_columns(actual_columns: list[str], candidate_columns: list[str]) -> tuple[list[str], list[str]]:
    """Return case-insensitive matched columns and missing candidates."""
    actual_by_upper = {col.upper(): col for col in actual_columns}
    kept = [actual_by_upper[col.upper()] for col in candidate_columns if col.upper() in actual_by_upper]
    missing = [col for col in candidate_columns if col.upper() not in actual_by_upper]
    return kept, missing


def write_minimal_parquet(
    source_csv: Path,
    output_parquet: Path,
    candidate_columns: list[str],
    dataset_label: str,
    summary_json_path: Path,
) -> None:
    """Read source CSV in chunks, keep existing candidate columns, and write parquet + summary."""
    if not source_csv.exists():
        raise FileNotFoundError(
            f"Missing source CSV: {source_csv}\n"
            "Run extraction first: python scripts/extract_and_inspect_acs.py"
        )

    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)

    header_columns = pd.read_csv(source_csv, nrows=0).columns.tolist()
    kept_columns, missing_columns = choose_existing_columns(header_columns, candidate_columns)

    if not kept_columns:
        raise RuntimeError(
            f"No candidate columns were found in source file: {source_csv}. "
            "Check column names in metadata summary before continuing."
        )

    print(f"[{dataset_label}] Keeping {len(kept_columns)} columns: {kept_columns}")
    print(f"[{dataset_label}] Missing {len(missing_columns)} candidate columns: {missing_columns}")

    writer: pq.ParquetWriter | None = None
    rows_written = 0

    try:
        for chunk in pd.read_csv(source_csv, usecols=kept_columns, chunksize=CHUNK_SIZE, low_memory=False):
            rows_written += len(chunk)
            table = pa.Table.from_pandas(chunk, preserve_index=False)

            if writer is None:
                writer = pq.ParquetWriter(output_parquet, table.schema, compression="snappy")
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()

    sample_df = pd.read_parquet(output_parquet).head(5)

    summary = {
        "dataset": dataset_label,
        "source_csv_path": str(source_csv),
        "output_parquet_path": str(output_parquet),
        "rows_written": int(rows_written),
        "columns_kept": kept_columns,
        "columns_missing_from_candidates": missing_columns,
        "number_of_columns_kept": len(kept_columns),
        "first_30_columns_kept": kept_columns[:30],
        "sample_rows_loaded_for_preview": int(len(sample_df)),
        "notes": (
            "Minimal intermediate file for later grounding work. "
            "No recoding, priors, or persona integration applied."
        ),
    }

    summary_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{dataset_label}] Wrote parquet: {output_parquet}")
    print(f"[{dataset_label}] Wrote summary: {summary_json_path}")


def main() -> None:
    """Run minimal ACS preprocessing for person and housing files."""
    project_root = Path(__file__).resolve().parents[1]

    person_csv = project_root / "data" / "raw" / "acs_pums" / "extracted" / "psam_p06.csv"
    housing_csv = project_root / "data" / "raw" / "acs_pums" / "extracted" / "psam_h06.csv"

    lookups_dir = project_root / "data" / "processed" / "lookups"
    metadata_dir = project_root / "data" / "processed" / "metadata"

    write_minimal_parquet(
        source_csv=person_csv,
        output_parquet=lookups_dir / "acs_person_minimal.parquet",
        candidate_columns=ACS_PERSON_CANDIDATE_COLUMNS,
        dataset_label="ACS person (CA)",
        summary_json_path=metadata_dir / "acs_person_minimal_summary.json",
    )

    write_minimal_parquet(
        source_csv=housing_csv,
        output_parquet=lookups_dir / "acs_housing_minimal.parquet",
        candidate_columns=ACS_HOUSING_CANDIDATE_COLUMNS,
        dataset_label="ACS housing (CA)",
        summary_json_path=metadata_dir / "acs_housing_minimal_summary.json",
    )


if __name__ == "__main__":
    main()
