"""Preprocess local ZIP->PUMA source into compact lookup parquet.

Scope:
- local file based only
- best-effort column matching
- graceful and explicit failure when source is missing or unusable
"""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any

import pandas as pd


RAW_DIR = "zip_puma_crosswalk"
LOOKUP_OUTPUT_NAME = "hud_zip_puma_lookup.parquet"
SUMMARY_OUTPUT_NAME = "zip_puma_crosswalk_preprocess_summary.json"
SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".parquet"}

ZIP_CANDIDATES = ["zip", "zipcode", "zip_code", "zcta", "postal"]
PUMA_CANDIDATES = ["puma", "puma_code", "puma20", "puma_2020", "puma_id"]
RATIO_CANDIDATES = ["res_ratio", "tot_ratio", "ratio", "share", "weight", "alloc"]
ALLOCATION_CANDIDATES = [
    "alloc",
    "ratio",
    "share",
    "weight",
    "arealand_part",
    "areawater_part",
    "area_part",
]


def _find_candidates(raw_path: Path) -> list[Path]:
    raw_path.mkdir(parents=True, exist_ok=True)
    return sorted(
        path
        for path in raw_path.glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _read_header(path: Path) -> tuple[list[str], str]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        xls = pd.ExcelFile(path)
        sheet = "Export Worksheet" if "Export Worksheet" in xls.sheet_names else xls.sheet_names[0]
        df = pd.read_excel(path, sheet_name=sheet, nrows=0)
        return [str(c) for c in df.columns], sheet
    if suffix == ".parquet":
        df = pd.read_parquet(path).head(0)
        return [str(c) for c in df.columns], "parquet"
    sep = _detect_text_separator(path, suffix)
    df = pd.read_csv(path, sep=sep, engine="python", nrows=0, encoding="utf-8-sig")
    return [str(c) for c in df.columns], "text"


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


def _detect(columns: list[str]) -> dict[str, list[str]]:
    lower_map = {str(col).lower(): str(col) for col in columns}

    def find(cands: list[str]) -> list[str]:
        out: list[str] = []
        for lower, original in lower_map.items():
            if any(token in lower for token in cands):
                out.append(original)
        return out

    return {
        "zip_cols": find(ZIP_CANDIDATES),
        "puma_cols": find(PUMA_CANDIDATES),
        "ratio_cols": find(RATIO_CANDIDATES),
        "allocation_cols": find(ALLOCATION_CANDIDATES),
    }


def _score(detected: dict[str, list[str]]) -> int:
    return (
        len(detected["zip_cols"]) * 4
        + len(detected["puma_cols"]) * 4
        + len(detected["ratio_cols"])
        + len(detected["allocation_cols"])
    )

def _pick_best_column(columns: list[str], *, kind: str) -> str:
    def rank(name: str) -> tuple[int, int]:
        lower = name.lower()
        score = 0
        if kind == "zip":
            if "geoid" in lower and "zcta" in lower:
                score += 100
            if "zip" in lower or "zcta" in lower:
                score += 20
            if "oid" in lower:
                score -= 25
        else:
            if "geoid" in lower and "puma" in lower:
                score += 100
            if "puma" in lower:
                score += 20
            if "oid" in lower:
                score -= 25

        # Prefer tighter, cleaner names among ties.
        return score, -len(name)

    return max(columns, key=rank)


def _pick_best_allocation_column(columns: list[str]) -> str | None:
    if not columns:
        return None

    def rank(name: str) -> tuple[int, int]:
        lower = name.lower()
        score = 0
        if "arealand_part" in lower:
            score += 100
        elif "area_part" in lower:
            score += 90
        elif "ratio" in lower:
            score += 80
        elif "share" in lower:
            score += 70
        elif "weight" in lower:
            score += 60
        elif "alloc" in lower:
            score += 50
        elif "areawater_part" in lower:
            score += 40
        return score, -len(name)

    return max(columns, key=rank)


def _select_best_source(candidates: list[Path]) -> tuple[Path, str, dict[str, list[str]], list[str]]:
    best: tuple[int, Path | None, str, dict[str, list[str]], list[str]] = (-1, None, "", {}, [])

    for path in candidates:
        columns, source_kind = _read_header(path)
        detected = _detect(columns)
        score = _score(detected)
        if score > best[0]:
            best = (score, path, source_kind, detected, columns)

    if best[1] is None:
        raise RuntimeError("Unable to select ZIP->PUMA source file.")

    if not best[3].get("zip_cols") or not best[3].get("puma_cols"):
        raise RuntimeError(
            f"Best source file does not contain detectable ZIP/PUMA columns: {best[1]}\n"
            f"Columns: {best[4]}"
        )

    return best[1], best[2], best[3], best[4]


def _read_full(path: Path, source_kind: str, usecols: list[str]) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        xls = pd.ExcelFile(path)
        sheet = "Export Worksheet" if "Export Worksheet" in xls.sheet_names else xls.sheet_names[0]
        return pd.read_excel(path, sheet_name=sheet, usecols=usecols, dtype="string")
    if suffix == ".parquet":
        return pd.read_parquet(path, columns=usecols).astype("string")
    sep = _detect_text_separator(path, suffix)
    return pd.read_csv(
        path,
        sep=sep,
        engine="python",
        usecols=usecols,
        encoding="utf-8-sig",
        dtype="string",
    )


def _normalize_zip(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    digits = text.str.replace(r"\D", "", regex=True)
    return digits.str.slice(0, 5).str.zfill(5)


def _normalize_puma(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.strip("'\"")
    digits = text.str.replace(r"\D", "", regex=True)
    # Keep 5-digit PUMA formatting when numeric-like; fallback to original cleaned text otherwise.
    # For 2020 GEOID PUMA values like 0607510, use the trailing 5-digit PUMA segment (07510).
    numeric_like = digits.str.len() > 0
    formatted = pd.Series(pd.NA, index=series.index, dtype="string")
    formatted.loc[numeric_like] = digits.loc[numeric_like].str.slice(-5).str.zfill(5)
    formatted.loc[~numeric_like] = text.loc[~numeric_like]
    return formatted


def _extract_state_code_from_puma(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.strip("'\"")
    digits = text.str.replace(r"\D", "", regex=True)

    # For GEOID PUMA values (state+PUMA, typically length >= 7), keep first 2 digits as state code.
    state = pd.Series(pd.NA, index=series.index, dtype="string")
    geoid_like = digits.str.len() >= 7
    state.loc[geoid_like] = digits.loc[geoid_like].str.slice(0, 2).str.zfill(2)
    return state


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    raw_path = project_root / "data" / "raw" / RAW_DIR
    lookups_dir = project_root / "data" / "processed" / "lookups"
    metadata_dir = project_root / "data" / "processed" / "metadata"
    lookups_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    candidates = _find_candidates(raw_path)
    if not candidates:
        raise FileNotFoundError(
            f"No ZIP->PUMA source file found in {raw_path}.\n"
            "Place a manual ZIP->PUMA crosswalk file there first."
        )

    best_file, source_kind, detected, header_cols = _select_best_source(candidates)
    zip_col = _pick_best_column(detected["zip_cols"], kind="zip")
    puma_col = _pick_best_column(detected["puma_cols"], kind="puma")
    ratio_cols = detected["ratio_cols"]
    allocation_cols = detected["allocation_cols"]
    selected_allocation_col = _pick_best_allocation_column(allocation_cols)

    usecols = [zip_col, puma_col] + [col for col in ratio_cols if col not in {zip_col, puma_col}]
    if selected_allocation_col and selected_allocation_col not in usecols:
        usecols.append(selected_allocation_col)
    raw_df = _read_full(best_file, source_kind, usecols=usecols)

    out = pd.DataFrame()
    out["zip_code"] = _normalize_zip(raw_df[zip_col])
    out["puma"] = _normalize_puma(raw_df[puma_col])
    out["puma_code"] = out["puma"]
    state_code = _extract_state_code_from_puma(raw_df[puma_col])
    if state_code.notna().any():
        out["state_code"] = state_code

    for col in ratio_cols:
        target = str(col).strip().lower()
        out[target] = pd.to_numeric(raw_df[col], errors="coerce")

    if selected_allocation_col:
        out["allocation"] = pd.to_numeric(raw_df[selected_allocation_col], errors="coerce")

    out = out.dropna(subset=["zip_code", "puma"])
    out = out[(out["zip_code"].str.len() == 5) & (out["puma"].str.len() > 0)]
    out = out.drop_duplicates().reset_index(drop=True)

    lookup_path = lookups_dir / LOOKUP_OUTPUT_NAME
    out.to_parquet(lookup_path, index=False)

    summary: dict[str, Any] = {
        "dataset": "Local ZIP->PUMA preprocessing",
        "source_directory": str(raw_path),
        "candidate_files": [str(path) for path in candidates],
        "selected_source_file": str(best_file),
        "selected_source_type": source_kind,
        "selected_zip_column": zip_col,
        "selected_puma_column": puma_col,
        "selected_ratio_columns": ratio_cols,
        "selected_allocation_column": selected_allocation_col,
        "header_columns": header_cols,
        "output_lookup_path": str(lookup_path),
        "rows_written": int(len(out)),
        "output_columns": out.columns.tolist(),
        "provenance_note": (
            "Source appears ZCTA-based (ZIP-like) rather than USPS ZIP-address based. "
            "Lookup uses this ZCTA bridge as best available local mapping."
        ),
        "notes": (
            "Best-effort local ZIP->PUMA preprocessing. "
            "No synthetic/fake PUMA assignment is performed."
        ),
    }

    summary_path = metadata_dir / SUMMARY_OUTPUT_NAME
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("ZIP->PUMA preprocessing complete.")
    print(f"Lookup: {lookup_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
