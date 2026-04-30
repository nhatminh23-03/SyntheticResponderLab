"""Geography-context normalization helpers (setup stage only).

This module builds a normalized internal geography bundle from HUD ZIP crosswalk lookups.
No persona-generation or simulation wiring is included in this step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from backend.data_sources.hud_zip_api import (
    HUDLookupError,
    lookup_zip_to_cbsa,
    lookup_zip_to_county,
    lookup_zip_to_tract,
)
from backend.schemas import GeographyContext


def build_geography_context_from_local_zip(zip_code: str) -> GeographyContext:
    """Build `GeographyContext` from local HUD parquet lookups.

    Behavior:
    - returns enriched context when local ZIP match exists
    - returns minimal ZIP-only context when files exist but ZIP has no row
    - returns graceful ZIP-only fallback when local files are missing
    """
    normalized_zip = _normalize_zip(zip_code)
    if not normalized_zip:
        return GeographyContext(zip_code=None, source="hud_local_crosswalk_invalid_zip")

    cbsa_path, county_path = _local_lookup_paths()
    if not cbsa_path.exists() or not county_path.exists():
        return GeographyContext(
            zip_code=normalized_zip,
            source="hud_local_crosswalk_files_missing",
        )

    try:
        cbsa_df = pd.read_parquet(cbsa_path, columns=[
            "zip_code", "cbsa_code", "cbsa_name", "res_ratio", "tot_ratio"
        ])
    except Exception:
        cbsa_df = pd.read_parquet(cbsa_path)

    try:
        county_df = pd.read_parquet(county_path, columns=[
            "zip_code", "county_fips", "county_name", "res_ratio", "tot_ratio"
        ])
    except Exception:
        county_df = pd.read_parquet(county_path)

    cbsa_row = _best_zip_match(cbsa_df, normalized_zip)
    county_row = _best_zip_match(county_df, normalized_zip)

    if cbsa_row is None and county_row is None:
        return GeographyContext(
            zip_code=normalized_zip,
            source="hud_local_crosswalk_no_match",
        )

    cbsa_code = _clean_text(_row_value(cbsa_row, "cbsa_code"))
    county_fips = _clean_text(_row_value(county_row, "county_fips"))
    puma_value = _derive_puma_from_local_assets(
        zip_code=normalized_zip,
        cbsa_code=cbsa_code,
        county_fips=county_fips,
    )

    return GeographyContext(
        zip_code=normalized_zip,
        county_fips=county_fips,
        county_name=_clean_text(_row_value(county_row, "county_name")),
        cbsa_code=cbsa_code,
        cbsa_name=_clean_text(_row_value(cbsa_row, "cbsa_name")),
        puma=puma_value,
        source="hud_local_crosswalk",
    )


def build_geography_context_from_zip(
    zip_code: str,
    token: Optional[str] = None,
    prefer_local: bool = True,
) -> GeographyContext:
    """Build normalized `GeographyContext` from HUD ZIP lookup helpers.

    Default behavior prefers local-file lookup first, then falls back to API.
    If both fail, returns a minimal ZIP-only context.
    """
    normalized_zip = _normalize_zip(zip_code)
    if not normalized_zip:
        return GeographyContext(zip_code=None, source="invalid_zip")

    if prefer_local:
        local_context = build_geography_context_from_local_zip(normalized_zip)
        if local_context.source == "hud_local_crosswalk":
            return local_context

    try:
        county = lookup_zip_to_county(zip_code=zip_code, token=token)
        cbsa = lookup_zip_to_cbsa(zip_code=zip_code, token=token)
        tract = lookup_zip_to_tract(zip_code=zip_code, token=token)

        return GeographyContext(
            zip_code=(county.get("zip_code") or cbsa.get("zip_code") or tract.get("zip_code") or normalized_zip),
            county_fips=county.get("county_fips"),
            county_name=county.get("county_name"),
            cbsa_code=cbsa.get("cbsa_code"),
            cbsa_name=cbsa.get("cbsa_name"),
            tract_code=tract.get("tract"),
            source="hud_zip_crosswalk_api",
        )
    except HUDLookupError:
        return GeographyContext(zip_code=normalized_zip, source="zip_only_fallback")


def _local_lookup_paths() -> tuple[Path, Path]:
    project_root = Path(__file__).resolve().parents[2]
    lookups_dir = project_root / "data" / "processed" / "lookups"
    return (
        lookups_dir / "hud_zip_cbsa_lookup.parquet",
        lookups_dir / "hud_zip_county_lookup.parquet",
    )


def _derive_puma_from_local_assets(
    zip_code: str,
    cbsa_code: Optional[str],
    county_fips: Optional[str],
) -> Optional[str]:
    """Best-effort local PUMA enrichment.

    Priority:
    1) direct local ZIP->PUMA lookup file if present,
    2) bridge from geo-aware priors when both PUMA and CBSA/county are available.
    """
    project_root = Path(__file__).resolve().parents[2]
    lookups_dir = project_root / "data" / "processed" / "lookups"

    direct_puma_path = lookups_dir / "hud_zip_puma_lookup.parquet"
    if direct_puma_path.exists():
        try:
            direct_df = pd.read_parquet(direct_puma_path)
            direct_row = _best_zip_match(direct_df, zip_code)
            puma_direct = _clean_text(_row_value(direct_row, "puma")) or _clean_text(_row_value(direct_row, "puma_code"))
            if puma_direct:
                return puma_direct
        except Exception:
            pass

    priors_dir = project_root / "data" / "processed" / "priors"
    bridge_files = [
        priors_dir / "household_size_priors_geo.parquet",
        priors_dir / "age_income_priors_geo.parquet",
        priors_dir / "ownership_home_type_priors_geo.parquet",
        priors_dir / "work_mode_hints_geo.parquet",
    ]

    for path in bridge_files:
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue

        puma_col = _first_existing_column(df, ["puma", "puma_code"])
        if puma_col is None:
            continue

        bridge_df = df.copy()
        bridge_df[puma_col] = bridge_df[puma_col].astype("string").map(_clean_text)
        bridge_df = bridge_df[bridge_df[puma_col].notna() & (bridge_df[puma_col] != "unknown")]
        if bridge_df.empty:
            continue

        # Prefer CBSA bridge when both columns exist and context has CBSA.
        cbsa_col = _first_existing_column(bridge_df, ["cbsa_code", "cbsa"])
        if cbsa_col and cbsa_code:
            bridge_df[cbsa_col] = bridge_df[cbsa_col].astype("string").map(_clean_text)
            cbsa_matched = bridge_df[bridge_df[cbsa_col] == _clean_text(cbsa_code)]
            if not cbsa_matched.empty:
                return _top_puma_from_rows(cbsa_matched, puma_col)

        # Fallback county bridge if present.
        county_col = _first_existing_column(bridge_df, ["county_fips", "county_code", "county"])
        if county_col and county_fips:
            bridge_df[county_col] = bridge_df[county_col].astype("string").map(_clean_text)
            county_matched = bridge_df[bridge_df[county_col] == _clean_text(county_fips)]
            if not county_matched.empty:
                return _top_puma_from_rows(county_matched, puma_col)

    return None


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    columns_lower = {str(col).lower(): str(col) for col in df.columns}
    for candidate in candidates:
        matched = columns_lower.get(candidate.lower())
        if matched:
            return matched
    return None


def _top_puma_from_rows(df: pd.DataFrame, puma_col: str) -> Optional[str]:
    if puma_col not in df.columns or df.empty:
        return None
    count_col = "count" if "count" in df.columns else None
    if count_col:
        grouped = (
            df[[puma_col, count_col]]
            .dropna()
            .groupby(puma_col, dropna=False)[count_col]
            .sum()
            .sort_values(ascending=False)
        )
        if len(grouped) > 0:
            return _clean_text(str(grouped.index[0]))

    value_counts = df[puma_col].dropna().astype("string").value_counts()
    if len(value_counts) > 0:
        return _clean_text(str(value_counts.index[0]))
    return None


def _normalize_zip(zip_code: str) -> str:
    text = (zip_code or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 5:
        return digits[:5]
    return ""


def _best_zip_match(df: pd.DataFrame, zip_code: str) -> Optional[dict]:
    if "zip_code" not in df.columns:
        return None

    local = df.copy()
    local["zip_code"] = local["zip_code"].astype("string").str.replace(r"\D", "", regex=True).str.slice(0, 5).str.zfill(5)
    matched = local[local["zip_code"] == zip_code]
    if matched.empty:
        return None
    matched = matched.copy()

    rank_cols = [
        col
        for col in ["allocation", "res_ratio", "tot_ratio", "ratio", "share", "weight", "arealand_part"]
        if col in matched.columns
    ]
    if rank_cols:
        for col in rank_cols:
            matched[col] = pd.to_numeric(matched[col], errors="coerce").fillna(0.0)
        matched = matched.sort_values(rank_cols, ascending=False)

    return matched.iloc[0].to_dict()


def _row_value(row: Optional[dict], key: str) -> Optional[str]:
    if row is None:
        return None
    value = row.get(key)
    if value is None:
        return None
    return str(value)


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip().strip("'\"")
    if not cleaned or cleaned.lower() in {"none", "null", "nan"}:
        return None
    return cleaned


__all__ = [
    "build_geography_context_from_local_zip",
    "build_geography_context_from_zip",
    "HUDLookupError",
]
