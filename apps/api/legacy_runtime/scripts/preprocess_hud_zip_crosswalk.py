"""Preprocess local HUD ZIP crosswalk Excel files into compact parquet lookups.

Scope:
- local-file based only (no HUD API)
- keep useful ZIP->CBSA and ZIP->county mapping columns
- write compact lookup parquet outputs + metadata summary
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


RAW_DIR_NAME = "hud_zip_crosswalk"
CBSA_FILE = "ZIP_CBSA_122025.xlsx"
COUNTY_FILE = "ZIP_COUNTY_122025.xlsx"
PREFERRED_SHEET = "Export Worksheet"


def _safe_read_excel(path: Path, sheet_name: str | None = None, **kwargs) -> pd.DataFrame:
    try:
        if sheet_name is None:
            return pd.read_excel(path, **kwargs)
        return pd.read_excel(path, sheet_name=sheet_name, **kwargs)
    except ImportError as exc:
        raise RuntimeError(
            "Excel support dependency missing. Install with: .venv-1/bin/python -m pip install openpyxl"
        ) from exc


def _load_primary_sheet(path: Path) -> tuple[pd.DataFrame, str]:
    xls = pd.ExcelFile(path)
    if PREFERRED_SHEET in xls.sheet_names:
        sheet = PREFERRED_SHEET
    elif not xls.sheet_names:
        raise RuntimeError(f"No sheets found in workbook: {path}")
    else:
        sheet = xls.sheet_names[0]

    # Read header first, then load only relevant columns for speed.
    header_df = _safe_read_excel(path, sheet_name=sheet, nrows=0)
    header_cols = [str(col).strip() for col in header_df.columns]
    wanted_candidates = {
        "ZIP",
        "zip",
        "zip_code",
        "CBSA",
        "cbsa",
        "cbsa_code",
        "CBSA_NAME",
        "cbsa_name",
        "METRO_NAME",
        "metro_name",
        "COUNTY",
        "county",
        "county_fips",
        "county_code",
        "COUNTY_NAME",
        "county_name",
        "USPS_ZIP_PREF_CITY",
        "zip_pref_city",
        "city",
        "USPS_ZIP_PREF_STATE",
        "zip_pref_state",
        "state",
        "RES_RATIO",
        "res_ratio",
        "res_share",
        "ratio_residential",
        "BUS_RATIO",
        "bus_ratio",
        "OTH_RATIO",
        "oth_ratio",
        "TOT_RATIO",
        "tot_ratio",
    }
    usecols = [col for col in header_cols if col in wanted_candidates]
    if not usecols:
        # Fall back to full load when workbook headers are unexpected.
        return _safe_read_excel(path, sheet_name=sheet), sheet

    return _safe_read_excel(path, sheet_name=sheet, usecols=usecols), sheet


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    return out


def _pick_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {str(col).lower(): str(col) for col in df.columns}
    for candidate in candidates:
        picked = lower_map.get(candidate.lower())
        if picked is not None:
            return picked
    return None


def _normalize_zip(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    digits = text.str.replace(r"\D", "", regex=True)
    return digits.str.slice(0, 5).str.zfill(5)


def _normalize_code(series: pd.Series, width: int | None = None) -> pd.Series:
    text = series.astype("string").str.strip()
    digits = text.str.replace(r"\D", "", regex=True)
    if width is not None:
        return digits.str.slice(0, width).str.zfill(width)
    return digits


def _build_cbsa_lookup(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    zip_col = _pick_existing(df, ["ZIP", "zip", "zip_code"])
    cbsa_col = _pick_existing(df, ["CBSA", "cbsa", "cbsa_code"])
    cbsa_name_col = _pick_existing(df, ["CBSA_NAME", "cbsa_name", "metro_name", "METRO_NAME"])

    res_ratio_col = _pick_existing(df, ["RES_RATIO", "res_ratio", "res_share", "ratio_residential"])
    bus_ratio_col = _pick_existing(df, ["BUS_RATIO", "bus_ratio"])
    oth_ratio_col = _pick_existing(df, ["OTH_RATIO", "oth_ratio"])
    tot_ratio_col = _pick_existing(df, ["TOT_RATIO", "tot_ratio"])

    city_col = _pick_existing(df, ["USPS_ZIP_PREF_CITY", "zip_pref_city", "city"])
    state_col = _pick_existing(df, ["USPS_ZIP_PREF_STATE", "zip_pref_state", "state"])

    if not zip_col or not cbsa_col:
        raise RuntimeError(
            f"Could not find required ZIP/CBSA columns. zip_col={zip_col}, cbsa_col={cbsa_col}. Columns: {list(df.columns)}"
        )

    out = pd.DataFrame()
    out["zip_code"] = _normalize_zip(df[zip_col])
    out["cbsa_code"] = _normalize_code(df[cbsa_col], width=5)
    out["cbsa_name"] = df[cbsa_name_col].astype("string").str.strip() if cbsa_name_col else pd.Series(pd.NA, index=df.index, dtype="string")

    if city_col:
        out["zip_pref_city"] = df[city_col].astype("string").str.strip()
    else:
        notes.append("No city column found for CBSA file.")
    if state_col:
        out["zip_pref_state"] = df[state_col].astype("string").str.strip()
    else:
        notes.append("No state column found for CBSA file.")

    if res_ratio_col:
        out["res_ratio"] = pd.to_numeric(df[res_ratio_col], errors="coerce")
    if bus_ratio_col:
        out["bus_ratio"] = pd.to_numeric(df[bus_ratio_col], errors="coerce")
    if oth_ratio_col:
        out["oth_ratio"] = pd.to_numeric(df[oth_ratio_col], errors="coerce")
    if tot_ratio_col:
        out["tot_ratio"] = pd.to_numeric(df[tot_ratio_col], errors="coerce")

    out = out.dropna(subset=["zip_code", "cbsa_code"])
    out = out[(out["zip_code"].str.len() == 5) & (out["cbsa_code"].str.len() == 5)]
    out = out.drop_duplicates().reset_index(drop=True)

    if not cbsa_name_col:
        notes.append("No CBSA name column found; cbsa_name kept as null.")

    return out, notes


def _build_county_lookup(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    zip_col = _pick_existing(df, ["ZIP", "zip", "zip_code"])
    county_col = _pick_existing(df, ["COUNTY", "county", "county_fips", "county_code"])
    county_name_col = _pick_existing(df, ["COUNTY_NAME", "county_name"])

    res_ratio_col = _pick_existing(df, ["RES_RATIO", "res_ratio", "res_share", "ratio_residential"])
    bus_ratio_col = _pick_existing(df, ["BUS_RATIO", "bus_ratio"])
    oth_ratio_col = _pick_existing(df, ["OTH_RATIO", "oth_ratio"])
    tot_ratio_col = _pick_existing(df, ["TOT_RATIO", "tot_ratio"])

    city_col = _pick_existing(df, ["USPS_ZIP_PREF_CITY", "zip_pref_city", "city"])
    state_col = _pick_existing(df, ["USPS_ZIP_PREF_STATE", "zip_pref_state", "state"])

    if not zip_col or not county_col:
        raise RuntimeError(
            f"Could not find required ZIP/COUNTY columns. zip_col={zip_col}, county_col={county_col}. Columns: {list(df.columns)}"
        )

    out = pd.DataFrame()
    out["zip_code"] = _normalize_zip(df[zip_col])
    out["county_fips"] = _normalize_code(df[county_col], width=5)
    out["county_name"] = (
        df[county_name_col].astype("string").str.strip()
        if county_name_col
        else pd.Series(pd.NA, index=df.index, dtype="string")
    )

    if city_col:
        out["zip_pref_city"] = df[city_col].astype("string").str.strip()
    else:
        notes.append("No city column found for county file.")
    if state_col:
        out["zip_pref_state"] = df[state_col].astype("string").str.strip()
    else:
        notes.append("No state column found for county file.")

    if res_ratio_col:
        out["res_ratio"] = pd.to_numeric(df[res_ratio_col], errors="coerce")
    if bus_ratio_col:
        out["bus_ratio"] = pd.to_numeric(df[bus_ratio_col], errors="coerce")
    if oth_ratio_col:
        out["oth_ratio"] = pd.to_numeric(df[oth_ratio_col], errors="coerce")
    if tot_ratio_col:
        out["tot_ratio"] = pd.to_numeric(df[tot_ratio_col], errors="coerce")

    out = out.dropna(subset=["zip_code", "county_fips"])
    out = out[(out["zip_code"].str.len() == 5) & (out["county_fips"].str.len() == 5)]
    out = out.drop_duplicates().reset_index(drop=True)

    if not county_name_col:
        notes.append("No county name column found; county_name kept as null.")

    return out, notes


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    raw_dir = project_root / "data" / "raw" / RAW_DIR_NAME
    lookups_dir = project_root / "data" / "processed" / "lookups"
    metadata_dir = project_root / "data" / "processed" / "metadata"

    lookups_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    cbsa_path = raw_dir / CBSA_FILE
    county_path = raw_dir / COUNTY_FILE

    missing = [str(path) for path in [cbsa_path, county_path] if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required HUD local crosswalk files:\n- " + "\n- ".join(missing)
        )

    cbsa_raw, cbsa_sheet = _load_primary_sheet(cbsa_path)
    county_raw, county_sheet = _load_primary_sheet(county_path)

    cbsa_raw = _normalize_columns(cbsa_raw)
    county_raw = _normalize_columns(county_raw)

    cbsa_lookup, cbsa_notes = _build_cbsa_lookup(cbsa_raw)
    county_lookup, county_notes = _build_county_lookup(county_raw)

    cbsa_output = lookups_dir / "hud_zip_cbsa_lookup.parquet"
    county_output = lookups_dir / "hud_zip_county_lookup.parquet"

    cbsa_lookup.to_parquet(cbsa_output, index=False)
    county_lookup.to_parquet(county_output, index=False)

    summary: dict[str, Any] = {
        "dataset": "HUD ZIP local crosswalk preprocessing",
        "source_files": {
            "cbsa": str(cbsa_path),
            "county": str(county_path),
        },
        "source_sheets_used": {
            "cbsa": cbsa_sheet,
            "county": county_sheet,
        },
        "outputs": {
            "hud_zip_cbsa_lookup": str(cbsa_output),
            "hud_zip_county_lookup": str(county_output),
        },
        "cbsa_lookup": {
            "rows": int(len(cbsa_lookup)),
            "columns": cbsa_lookup.columns.tolist(),
            "notes": cbsa_notes,
        },
        "county_lookup": {
            "rows": int(len(county_lookup)),
            "columns": county_lookup.columns.tolist(),
            "notes": county_notes,
        },
        "notes": (
            "Local-file preprocessing only. "
            "No HUD API dependency in this workflow step. "
            "Column matching is best-effort and records notes when expected name fields are absent."
        ),
    }

    summary_path = metadata_dir / "hud_zip_crosswalk_preprocess_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"HUD ZIP crosswalk preprocessing complete.")
    print(f"CBSA lookup: {cbsa_output}")
    print(f"County lookup: {county_output}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
