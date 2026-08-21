"""Inspect local HUD ZIP crosswalk Excel files and write metadata summary.

Scope:
- local file detection only (no HUD API usage)
- workbook/sheet inspection
- tiny sample reads for schema visibility
- metadata summary output for downstream preprocessing
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


RAW_DIR_NAME = "hud_zip_crosswalk"
SAMPLE_ROWS = 25
EXPECTED_FILES = [
    "ZIP_CBSA_122025.xlsx",
    "ZIP_COUNTY_122025.xlsx",
]


def _find_files(raw_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for filename in EXPECTED_FILES:
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Missing required HUD file: {path}\n"
                f"Please place manually downloaded file under data/raw/{RAW_DIR_NAME}/"
            )
        found[filename] = path
    return found


def _safe_excel_file(path: Path) -> pd.ExcelFile:
    try:
        return pd.ExcelFile(path)
    except ImportError as exc:
        raise RuntimeError(
            "Excel support dependency missing. Install with: .venv-1/bin/python -m pip install openpyxl"
        ) from exc


def _detect_likely_columns(columns: list[str]) -> dict[str, list[str]]:
    lower = {col.lower(): col for col in columns}

    def matches(tokens: list[str]) -> list[str]:
        out: list[str] = []
        for key, original in lower.items():
            if all(token in key for token in tokens):
                out.append(original)
        return out

    zip_cols = [c for c in columns if "zip" in c.lower()]
    county_code_cols = [c for c in columns if "county" in c.lower() and "name" not in c.lower()]
    county_name_cols = matches(["county", "name"])
    cbsa_code_cols = [c for c in columns if "cbsa" in c.lower() and "name" not in c.lower()]
    cbsa_name_cols = matches(["cbsa", "name"]) + matches(["metro", "name"])
    tract_cols = [c for c in columns if "tract" in c.lower()]
    ratio_cols = [c for c in columns if "ratio" in c.lower() or "share" in c.lower() or "alloc" in c.lower()]

    return {
        "zip_columns": zip_cols,
        "county_fips_columns": county_code_cols,
        "county_name_columns": county_name_cols,
        "cbsa_code_columns": cbsa_code_cols,
        "cbsa_name_columns": cbsa_name_cols,
        "tract_columns": tract_cols,
        "ratio_or_share_columns": ratio_cols,
    }


def _inspect_one_file(path: Path) -> dict[str, Any]:
    xls = _safe_excel_file(path)
    workbook = {
        "file": str(path),
        "sheet_names": xls.sheet_names,
        "sheet_inspection": [],
    }

    for sheet_name in xls.sheet_names:
        sample_df = pd.read_excel(path, sheet_name=sheet_name, nrows=SAMPLE_ROWS)
        columns = [str(col) for col in sample_df.columns]
        workbook["sheet_inspection"].append(
            {
                "sheet_name": sheet_name,
                "sample_rows": int(len(sample_df)),
                "column_count": int(len(columns)),
                "columns": columns,
                "likely_columns": _detect_likely_columns(columns),
                "sample_preview": sample_df.head(5).to_dict(orient="records"),
            }
        )

    return workbook


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    raw_dir = project_root / "data" / "raw" / RAW_DIR_NAME
    metadata_dir = project_root / "data" / "processed" / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    files = _find_files(raw_dir)
    inspections = {name: _inspect_one_file(path) for name, path in files.items()}

    summary = {
        "dataset": "HUD ZIP local crosswalk (manual files)",
        "source_directory": str(raw_dir),
        "required_files": EXPECTED_FILES,
        "inspected_files": inspections,
        "notes": (
            "This is a local-file inspection step only. "
            "No HUD API calls are made. "
            "Column naming can vary by release; preprocessing step uses defensive matching."
        ),
    }

    output_path = metadata_dir / "hud_zip_crosswalk_summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"HUD ZIP crosswalk inspection complete. Summary written to: {output_path}")


if __name__ == "__main__":
    main()
