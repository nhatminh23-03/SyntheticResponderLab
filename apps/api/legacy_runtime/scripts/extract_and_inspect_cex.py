"""Extract BLS CEX archives and write a lightweight file-inspection metadata summary.

Scope:
- extraction + discovery + tiny sampling only
- no preprocessing
- no persona/simulation wiring
"""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pandas as pd


SAMPLE_ROWS = 50
LIKELY_TABULAR_SUFFIXES = {".csv", ".txt", ".dat", ".tsv", ".xpt", ".sas7bdat"}


def unzip_archive(archive_path: Path, destination_dir: Path) -> None:
    """Extract one zip archive into destination folder."""
    if not archive_path.exists():
        raise FileNotFoundError(f"Missing archive: {archive_path}")

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(destination_dir)
    except zipfile.BadZipFile as error:
        raise RuntimeError(
            "Invalid or corrupted CEX archive detected. "
            f"Archive: {archive_path}. "
            "Please verify the manual download files and rerun: bash scripts/download_cex.sh"
        ) from error


def list_extracted_files(root_dir: Path) -> list[Path]:
    """Recursively list all extracted files under root."""
    return sorted([path for path in root_dir.rglob("*") if path.is_file()])


def is_likely_tabular(path: Path) -> bool:
    """Return True when file extension suggests table-like content."""
    return path.suffix.lower() in LIKELY_TABULAR_SUFFIXES


def inspect_tabular_file(path: Path, sample_rows: int = SAMPLE_ROWS) -> dict:
    """Inspect small sample where feasible.

    For CSV/TXT/DAT/TSV we attempt a tiny pandas read with separator inference.
    For XPT/SAS7BDAT we report metadata only (no heavy parser dependency required).
    """
    suffix = path.suffix.lower()

    base = {
        "path": str(path),
        "size_bytes": int(path.stat().st_size),
        "suffix": suffix,
        "inspection_status": "not_attempted",
        "inspection_note": None,
    }

    if suffix in {".xpt", ".sas7bdat"}:
        base["inspection_status"] = "metadata_only"
        base["inspection_note"] = "SAS transport/binary detected. Full parsing deferred to preprocessing stage."
        return base

    if suffix not in {".csv", ".txt", ".dat", ".tsv"}:
        base["inspection_status"] = "metadata_only"
        base["inspection_note"] = "Unsupported lightweight inspection type for this suffix."
        return base

    try:
        sample_df = pd.read_csv(path, nrows=sample_rows, sep=None, engine="python", low_memory=False)
    except UnicodeDecodeError:
        sample_df = pd.read_csv(
            path,
            nrows=sample_rows,
            sep=None,
            engine="python",
            low_memory=False,
            encoding="latin-1",
        )
    except Exception as error:
        base["inspection_status"] = "read_failed"
        base["inspection_note"] = f"Sample read failed: {error}"
        return base

    columns = sample_df.columns.tolist()
    base.update(
        {
            "inspection_status": "sampled",
            "inspection_note": "Tiny sample loaded successfully.",
            "rows_loaded_for_inspection": int(len(sample_df)),
            "number_of_columns": int(len(columns)),
            "first_30_column_names": columns[:30],
            "rough_dtypes": {column: str(dtype) for column, dtype in sample_df.dtypes.items()},
        }
    )
    return base


def summarize_detected_files(paths: list[Path], project_root: Path) -> list[dict]:
    """Return path and size metadata for all detected extracted files."""
    output: list[dict] = []
    for path in paths:
        output.append(
            {
                "path": str(path),
                "path_relative_to_project": str(path.relative_to(project_root)),
                "size_bytes": int(path.stat().st_size),
                "suffix": path.suffix.lower(),
            }
        )
    return output


def build_notes(likely_tabular_files: list[Path]) -> str:
    """Create a short guidance note about likely useful CEX inputs."""
    if not likely_tabular_files:
        return (
            "No likely tabular files were detected by extension scan. "
            "Verify extracted archive contents before preprocessing."
        )

    names = [path.name.lower() for path in likely_tabular_files]
    interview_hint = [name for name in names if "fmli" in name or "interview" in name or "mtbi" in name]
    diary_hint = [name for name in names if "expd" in name or "diary" in name or "mtbd" in name]

    guidance_parts = [
        "Likely useful files for affordability/spending realism are interview household/income tables "
        "and detailed expenditure tables.",
    ]
    if interview_hint:
        guidance_parts.append("Interview-like candidates detected (e.g., FMLI/Interview-related filenames).")
    if diary_hint:
        guidance_parts.append("Diary/expenditure-like candidates detected (e.g., EXPD/Diary-related filenames).")

    guidance_parts.append("This stage only inspects structure; variable-level mapping is next.")
    return " ".join(guidance_parts)


def main() -> None:
    """Extract CEX archives and write metadata summary JSON."""
    project_root = Path(__file__).resolve().parents[1]

    raw_dir = project_root / "data" / "raw" / "cex"
    extracted_root = raw_dir / "extracted"
    extracted_interview = extracted_root / "interview"
    extracted_diary = extracted_root / "diary"

    output_dir = project_root / "data" / "processed" / "metadata"
    output_path = output_dir / "cex_summary.json"

    interview_archive = raw_dir / "cex_interview_2024.zip"
    diary_archive = raw_dir / "cex_diary_2024.zip"

    for archive_path in [interview_archive, diary_archive]:
        if not archive_path.exists():
            raise FileNotFoundError(
                "Required CEX archive missing. "
                f"Expected file: {archive_path}\n"
                "Run: bash scripts/download_cex.sh"
            )

    extracted_interview.mkdir(parents=True, exist_ok=True)
    extracted_diary.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    unzip_archive(interview_archive, extracted_interview)
    unzip_archive(diary_archive, extracted_diary)

    detected_files = list_extracted_files(extracted_root)
    likely_tabular_files = [path for path in detected_files if is_likely_tabular(path)]

    sample_inspection = [inspect_tabular_file(path) for path in likely_tabular_files]

    summary = {
        "dataset": "BLS Consumer Expenditure Survey (CEX) PUMD CSV 2024",
        "source_archive_paths": {
            "interview": str(interview_archive),
            "diary": str(diary_archive),
        },
        "extracted_directories": {
            "root": str(extracted_root),
            "interview": str(extracted_interview),
            "diary": str(extracted_diary),
        },
        "detected_files": summarize_detected_files(detected_files, project_root=project_root),
        "likely_tabular_files": [str(path) for path in likely_tabular_files],
        "sample_inspection_notes": sample_inspection,
        "notes": build_notes(likely_tabular_files),
    }

    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"CEX extraction + inspection complete. Summary written to: {output_path}")


if __name__ == "__main__":
    main()
