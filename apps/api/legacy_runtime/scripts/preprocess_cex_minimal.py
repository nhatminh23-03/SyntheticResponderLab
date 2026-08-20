"""Minimal CEX preprocessing for affordability grounding.

Scope:
- read family-level interview/diary tables (FMLI/FMLD) from extracted CEX files
- keep a compact affordability-focused subset
- write small parquet outputs + metadata summary

Non-goals:
- no persona integration
- no simulation changes
- no final priors in this step
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


CHUNK_SIZE = 100_000

OUTPUT_COLUMNS = [
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


def find_family_files(root_dir: Path, prefix: str) -> list[Path]:
    """Find family-level sas7bdat files by filename prefix."""
    if not root_dir.exists():
        return []
    return sorted(
        path
        for path in root_dir.rglob("*.sas7bdat")
        if path.is_file() and path.name.lower().startswith(prefix.lower())
    )


def _empty_series_for(chunk: pd.DataFrame) -> pd.Series:
    return pd.Series([pd.NA] * len(chunk), index=chunk.index)


def _coalesce_columns(chunk: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """Return first non-null value across candidate columns, row-wise."""
    out = _empty_series_for(chunk)
    for col in candidates:
        if col in chunk.columns:
            out = out.where(out.notna(), chunk[col])
    return out


def _build_minimal_chunk(chunk: pd.DataFrame, dataset_label: str, source_file: str) -> pd.DataFrame:
    """Build one standardized minimal chunk from raw CEX chunk."""
    out = pd.DataFrame(index=chunk.index)

    out["household_id"] = _coalesce_columns(chunk, ["NEWID"])
    out["weight"] = _coalesce_columns(chunk, ["FINLWT21", "FINLWT20", "FINLWT22", "FINLWT"])

    out["income_before_tax"] = _coalesce_columns(chunk, ["FINCBTAX", "FINCBEFX"])
    out["income_after_tax"] = _coalesce_columns(chunk, ["FINATTX", "FINATTXM"])

    out["wage_income"] = _coalesce_columns(chunk, ["FWAGEX", "FWAGEXM"])
    out["salary_income"] = _coalesce_columns(chunk, ["FSALARYX"])

    out["income_rank"] = _coalesce_columns(chunk, ["INC_RANK", "INC_RNKM", "INC_RNK5", "INC_RNK4", "INC_RNK3"])

    out["family_size"] = _coalesce_columns(chunk, ["FAM_SIZE"])
    out["tenure_code"] = _coalesce_columns(chunk, ["CUTENURE"])

    out["rent_net"] = _coalesce_columns(chunk, ["NETRENTX", "NETRENTB", "NETRNTBX"])

    out["housing_total"] = _coalesce_columns(chunk, ["HOUSPQ", "HOUSCQ", "EHOUSNGP", "EHOUSNGC", "HOUSKEEP"])
    out["shelter_total"] = _coalesce_columns(chunk, ["SHELTPQ", "SHELTCQ", "ESHELTRP", "ESHELTRC"])
    out["utilities_total"] = _coalesce_columns(
        chunk,
        ["UTILPQ", "UTILCQ", "UTILOWNP", "UTILOWNC", "UTILRNTP", "UTILRNTC"],
    )

    out["total_expenditure"] = _coalesce_columns(
        chunk,
        ["TOTEXPPQ", "TOTEXPCQ", "ETOTALP", "ETOTALC", "OCCEXPNX"],
    )
    out["food_total"] = _coalesce_columns(chunk, ["FOODTOT"])

    out["source_dataset"] = dataset_label
    out["source_file"] = source_file

    # Enforce stable dtypes across chunks/files to avoid parquet schema drift.
    text_columns = ["household_id", "income_rank", "tenure_code", "source_dataset", "source_file"]
    numeric_columns = [
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

    for col in text_columns:
        out[col] = out[col].astype("string")

    for col in numeric_columns:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # Keep stable column order.
    out = out[OUTPUT_COLUMNS]
    return out


def _write_empty_parquet(output_path: Path) -> None:
    empty_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
    table = pa.Table.from_pandas(empty_df, preserve_index=False)
    pq.write_table(table, output_path, compression="snappy")


def process_family_dataset(
    files: list[Path],
    dataset_label: str,
    project_root: Path,
    output_parquet_path: Path,
) -> dict[str, Any]:
    """Process many family-level sas files into one compact parquet output."""
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)

    if not files:
        _write_empty_parquet(output_parquet_path)
        return {
            "dataset": dataset_label,
            "rows_written": 0,
            "files_detected": [],
            "files_processed": [],
            "files_skipped": [],
            "errors": ["No matching source files found."],
            "output_parquet_path": str(output_parquet_path),
        }

    rows_written = 0
    files_processed: list[dict[str, Any]] = []
    files_skipped: list[dict[str, Any]] = []
    errors: list[str] = []

    writer: pq.ParquetWriter | None = None

    try:
        for file_path in files:
            rel_path = str(file_path.relative_to(project_root))
            file_rows = 0
            file_columns_seen: list[str] = []
            try:
                chunk_iter = pd.read_sas(file_path, format="sas7bdat", encoding="latin-1", chunksize=CHUNK_SIZE)
                for chunk_index, chunk in enumerate(chunk_iter, start=1):
                    if chunk_index == 1:
                        file_columns_seen = [str(c) for c in chunk.columns]

                    minimal_chunk = _build_minimal_chunk(
                        chunk=chunk,
                        dataset_label=dataset_label,
                        source_file=rel_path,
                    )

                    file_rows += len(minimal_chunk)
                    rows_written += len(minimal_chunk)

                    table = pa.Table.from_pandas(minimal_chunk, preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(output_parquet_path, table.schema, compression="snappy")
                    writer.write_table(table)

                files_processed.append(
                    {
                        "file": rel_path,
                        "rows_written": int(file_rows),
                        "columns_seen_first_chunk": file_columns_seen[:120],
                    }
                )
            except Exception as error:
                files_skipped.append({"file": rel_path, "reason": str(error)})
                errors.append(f"Failed to parse {rel_path}: {error}")
    finally:
        if writer is not None:
            writer.close()

    if rows_written == 0:
        # Ensure output file exists even if all files failed.
        _write_empty_parquet(output_parquet_path)

    return {
        "dataset": dataset_label,
        "rows_written": int(rows_written),
        "files_detected": [str(path.relative_to(project_root)) for path in files],
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "errors": errors,
        "output_parquet_path": str(output_parquet_path),
    }


def main() -> None:
    """Run minimal CEX preprocessing for interview/diary family-level files."""
    project_root = Path(__file__).resolve().parents[1]

    interview_root = project_root / "data" / "raw" / "cex" / "extracted" / "interview"
    diary_root = project_root / "data" / "raw" / "cex" / "extracted" / "diary"

    if not interview_root.exists() or not diary_root.exists():
        raise FileNotFoundError(
            "CEX extracted directories missing. "
            "Run extraction first: python scripts/extract_and_inspect_cex.py"
        )

    lookups_dir = project_root / "data" / "processed" / "lookups"
    metadata_dir = project_root / "data" / "processed" / "metadata"
    lookups_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    interview_files = find_family_files(interview_root, prefix="fmli")
    diary_files = find_family_files(diary_root, prefix="fmld")

    if not interview_files:
        raise FileNotFoundError(
            f"No FMLI files found under: {interview_root}. "
            "Check extraction outputs in data/raw/cex/extracted/interview/."
        )

    if not diary_files:
        raise FileNotFoundError(
            f"No FMLD files found under: {diary_root}. "
            "Check extraction outputs in data/raw/cex/extracted/diary/."
        )

    interview_output = lookups_dir / "cex_interview_minimal.parquet"
    diary_output = lookups_dir / "cex_diary_minimal.parquet"

    interview_summary = process_family_dataset(
        files=interview_files,
        dataset_label="cex_interview_family",
        project_root=project_root,
        output_parquet_path=interview_output,
    )

    diary_summary = process_family_dataset(
        files=diary_files,
        dataset_label="cex_diary_family",
        project_root=project_root,
        output_parquet_path=diary_output,
    )

    summary = {
        "dataset": "BLS CEX minimal affordability preprocessing",
        "source_roots": {
            "interview": str(interview_root),
            "diary": str(diary_root),
        },
        "output_files": {
            "cex_interview_minimal": str(interview_output),
            "cex_diary_minimal": str(diary_output),
        },
        "standard_output_columns": OUTPUT_COLUMNS,
        "interview": interview_summary,
        "diary": diary_summary,
        "notes": (
            "Minimal affordability layer from family-level CEX tables (FMLI/FMLD). "
            "No final priors, no persona wiring, and no simulation integration in this step."
        ),
    }

    summary_path = metadata_dir / "cex_minimal_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"CEX minimal preprocessing complete. Summary written to: {summary_path}")
    print(f"Interview output: {interview_output}")
    print(f"Diary output: {diary_output}")


if __name__ == "__main__":
    main()
