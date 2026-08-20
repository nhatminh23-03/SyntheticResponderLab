"""Inspect local ZIP->PUMA crosswalk source files and write metadata summary.

Scope:
- local file detection only
- no simulation/persona wiring
- tiny schema/sample inspection for manual source validation
"""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any

import pandas as pd


RAW_DIR = "zip_puma_crosswalk"
OUTPUT_SUMMARY = "zip_puma_crosswalk_summary.json"
SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".parquet"}
SAMPLE_ROWS = 25

ZIP_COLUMN_CANDIDATES = [
    "zip",
    "zipcode",
    "zip_code",
    "zcta",
    "postal",
]
PUMA_COLUMN_CANDIDATES = [
    "puma",
    "puma_code",
    "puma20",
    "puma_2020",
    "puma_id",
]
ALLOCATION_COLUMN_CANDIDATES = [
    "alloc",
    "ratio",
    "share",
    "weight",
    "arealand_part",
    "areawater_part",
    "area_part",
]


def _find_candidate_files(raw_path: Path) -> list[Path]:
    raw_path.mkdir(parents=True, exist_ok=True)
    return sorted(
        path
        for path in raw_path.glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _read_sample(path: Path) -> tuple[pd.DataFrame, str, str | None]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        xls = pd.ExcelFile(path)
        sheet = "Export Worksheet" if "Export Worksheet" in xls.sheet_names else xls.sheet_names[0]
        return pd.read_excel(path, sheet_name=sheet, nrows=SAMPLE_ROWS), sheet, None
    if suffix == ".parquet":
        return pd.read_parquet(path).head(SAMPLE_ROWS), "parquet", None
    sep = _detect_text_separator(path, suffix)
    return (
        pd.read_csv(path, nrows=SAMPLE_ROWS, sep=sep, engine="python", encoding="utf-8-sig"),
        "text",
        sep,
    )


def _detect_text_separator(path: Path, suffix: str) -> str | None:
    if suffix == ".tsv":
        return "\t"

    header_line = path.open("r", encoding="utf-8-sig", errors="ignore").readline()
    if "|" in header_line:
        return "|"
    if "\t" in header_line:
        return "\t"

    try:
        sniffed = csv.Sniffer().sniff(header_line, delimiters=",|\t;")
        return sniffed.delimiter
    except Exception:
        return None


def _detect_columns(columns: list[str]) -> dict[str, list[str]]:
    lower_cols = [str(col).lower() for col in columns]
    zip_like = [columns[i] for i, col in enumerate(lower_cols) if any(token in col for token in ZIP_COLUMN_CANDIDATES)]
    puma_like = [columns[i] for i, col in enumerate(lower_cols) if any(token in col for token in PUMA_COLUMN_CANDIDATES)]
    ratio_like = [columns[i] for i, col in enumerate(lower_cols) if any(token in col for token in ["ratio", "share", "weight", "alloc"])]
    allocation_like = [
        columns[i]
        for i, col in enumerate(lower_cols)
        if any(token in col for token in ALLOCATION_COLUMN_CANDIDATES)
    ]
    return {
        "zip_like_columns": zip_like,
        "puma_like_columns": puma_like,
        "ratio_like_columns": ratio_like,
        "allocation_like_columns": allocation_like,
    }


def _score_detected(detected: dict[str, list[str]]) -> int:
    return (
        len(detected["zip_like_columns"]) * 3
        + len(detected["puma_like_columns"]) * 3
        + len(detected["ratio_like_columns"])
        + len(detected["allocation_like_columns"])
    )


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    raw_path = project_root / "data" / "raw" / RAW_DIR
    metadata_dir = project_root / "data" / "processed" / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    candidates = _find_candidate_files(raw_path)
    if not candidates:
        raise FileNotFoundError(
            f"No ZIP->PUMA source file found in {raw_path}.\n"
            "Please place a manually downloaded crosswalk file (csv/xlsx/parquet) with ZIP and PUMA columns there."
        )

    inspected: list[dict[str, Any]] = []
    best_file: str | None = None
    best_score = -1

    for path in candidates:
        sample_df, source_sheet, detected_delimiter = _read_sample(path)
        columns = [str(col) for col in sample_df.columns]
        detected = _detect_columns(columns)
        score = _score_detected(detected)
        if score > best_score:
            best_score = score
            best_file = str(path)

        inspected.append(
            {
                "file": str(path),
                "suffix": path.suffix.lower(),
                "sheet_or_source": source_sheet,
                "detected_delimiter": detected_delimiter,
                "sample_rows": int(len(sample_df)),
                "columns": columns,
                "detected": detected,
                "detection_score": score,
                "sample_preview": sample_df.head(5).to_dict(orient="records"),
            }
        )

    summary = {
        "dataset": "Local ZIP->PUMA crosswalk inspection",
        "source_directory": str(raw_path),
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "candidate_files": [str(path) for path in candidates],
        "best_candidate_file": best_file,
        "inspected_files": inspected,
        "provenance_note": (
            "The Census TAB20 file is ZCTA-based (ZIP-like), not USPS ZIP-address based. "
            "Using ZCTA as best-available local ZIP-like bridge for geography enrichment."
        ),
        "notes": (
            "This is a setup-only inspection step. "
            "No fake mapping is generated. Preprocess selects best candidate by ZIP/PUMA column detectability."
        ),
    }

    output_path = metadata_dir / OUTPUT_SUMMARY
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"ZIP->PUMA inspection complete. Summary written to: {output_path}")


if __name__ == "__main__":
    main()
