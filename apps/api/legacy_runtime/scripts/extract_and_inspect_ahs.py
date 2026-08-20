"""Extract AHS archive and write a small schema-inspection metadata summary."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pandas as pd


SAMPLE_ROWS = 50


def unzip_archive(archive_path: Path, destination_dir: Path) -> None:
    """Extract one zip archive into destination folder."""
    if not archive_path.exists():
        raise FileNotFoundError(f"Missing archive: {archive_path}")

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(destination_dir)
    except zipfile.BadZipFile as error:
        raise RuntimeError(
            "Invalid or corrupted AHS archive detected. "
            f"Archive: {archive_path}. "
            "Please re-download using: bash scripts/download_ahs.sh"
        ) from error


def find_csv_files(root_dir: Path) -> list[Path]:
    """Recursively locate CSV files under extracted root."""
    return sorted(
        [
            path
            for path in root_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".csv"
        ]
    )


def inspect_csv(csv_path: Path, sample_rows: int = SAMPLE_ROWS) -> dict:
    """Read a tiny sample of one CSV and return lightweight schema metadata."""
    sample_df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)
    column_names = sample_df.columns.tolist()

    return {
        "csv_path": str(csv_path),
        "rows_loaded_for_inspection": int(len(sample_df)),
        "number_of_columns": int(len(column_names)),
        "first_30_column_names": column_names[:30],
        "rough_dtypes": {column: str(dtype) for column, dtype in sample_df.dtypes.items()},
    }


def main() -> None:
    """Extract AHS archive and write metadata summary JSON."""
    project_root = Path(__file__).resolve().parents[1]
    raw_dir = project_root / "data" / "raw" / "ahs"
    extracted_dir = raw_dir / "extracted"
    output_dir = project_root / "data" / "processed" / "metadata"
    output_path = output_dir / "ahs_summary.json"

    archive_path = raw_dir / "AHS 2023 National PUF v1.1 Flat CSV.zip"
    if not archive_path.exists():
        raise FileNotFoundError(
            "Required AHS archive missing. "
            f"Expected file: {archive_path}\n"
            "Run: bash scripts/download_ahs.sh"
        )

    extracted_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    unzip_archive(archive_path, extracted_dir)

    csv_files = find_csv_files(extracted_dir)
    if not csv_files:
        raise FileNotFoundError(
            "No CSV files were detected after extraction. "
            f"Checked path: {extracted_dir}"
        )

    inspections = [inspect_csv(csv_path) for csv_path in csv_files]

    summary = {
        "dataset": "AHS 2023 National PUF v1.1 Flat CSV",
        "source_archive_path": str(archive_path),
        "extracted_root": str(extracted_dir),
        "detected_csv_files": [str(path) for path in csv_files],
        "files": inspections,
        "notes": (
            "Schema-only inspection using small row samples. "
            "No full-load preprocessing performed."
        ),
    }

    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"AHS extraction + inspection complete. Summary written to: {output_path}")


if __name__ == "__main__":
    main()
