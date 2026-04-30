"""Best-effort geography-to-prior filtering adapter (setup stage only).

This module narrows prior tables using a `GeographyContext` when geography columns
exist in those prior tables. It is intentionally defensive:
- prefers county-level filtering,
- falls back to CBSA-level filtering,
- falls back to global/unfiltered when geo columns are absent or no rows match.

No persona/simulation wiring is done here.
"""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

from backend.schemas import GeographyContext


COUNTY_COLUMN_CANDIDATES = [
    "county_fips",
    "county_code",
    "county",
    "county_name",
]
PUMA_COLUMN_CANDIDATES = [
    "puma",
    "puma_code",
]
CBSA_COLUMN_CANDIDATES = [
    "cbsa_code",
    "cbsa",
    "cbsa_name",
    "metro_code",
    "metro",
]


def summarize_geography_filter_result(
    *,
    prior_table_name: str,
    filter_level_used: str,
    row_count_before: int,
    row_count_after: int,
    notes: str,
) -> dict:
    """Build compact debug summary for one prior table geography filtering pass."""
    return {
        "prior_table_name": prior_table_name,
        "filter_level_used": filter_level_used,
        "row_count_before": int(row_count_before),
        "row_count_after": int(row_count_after),
        "narrowed": bool(row_count_after < row_count_before),
        "notes": notes,
    }


def filter_prior_table_by_geography(
    prior_df: pd.DataFrame,
    geography_context: GeographyContext,
    available_geo_columns: Optional[Iterable[str]] = None,
) -> tuple[pd.DataFrame, dict]:
    """Filter a prior table by geography context (county preferred, then CBSA).

    Returns:
        tuple(filtered_df, debug_summary)
    """
    before = len(prior_df)
    geo_columns = set(available_geo_columns or prior_df.columns)

    county_cols = [col for col in COUNTY_COLUMN_CANDIDATES if col in geo_columns]
    puma_cols = [col for col in PUMA_COLUMN_CANDIDATES if col in geo_columns]
    cbsa_cols = [col for col in CBSA_COLUMN_CANDIDATES if col in geo_columns]

    county_values = _candidate_values(
        geography_context.county_fips,
        geography_context.county_name,
    )
    cbsa_values = _candidate_values(
        geography_context.cbsa_code,
        geography_context.cbsa_name,
    )
    puma_values = _candidate_values(
        getattr(geography_context, "puma_code", None),
        getattr(geography_context, "puma", None),
    )

    # 0) Prefer county where available and context supports it.

    if county_cols and county_values:
        filtered = _filter_by_columns(prior_df, county_cols, county_values)
        if not filtered.empty:
            note = f"county filtering applied using columns={county_cols} values={county_values}"
            return filtered, summarize_geography_filter_result(
                prior_table_name="",
                filter_level_used="county",
                row_count_before=before,
                row_count_after=len(filtered),
                notes=note,
            )
        note = (
            f"county columns found ({county_cols}) but no matching rows for {county_values}; "
            "falling back to global"
        )
        return prior_df, summarize_geography_filter_result(
            prior_table_name="",
            filter_level_used="global",
            row_count_before=before,
            row_count_after=before,
            notes=note,
        )

    # 1) If county unavailable, use puma when possible.
    if puma_cols and puma_values:
        filtered = _filter_by_columns(prior_df, puma_cols, puma_values)
        if not filtered.empty:
            note = f"PUMA filtering applied using columns={puma_cols} values={puma_values}"
            return filtered, summarize_geography_filter_result(
                prior_table_name="",
                filter_level_used="puma",
                row_count_before=before,
                row_count_after=len(filtered),
                notes=note,
            )
        note = (
            f"PUMA columns found ({puma_cols}) but no matching rows for {puma_values}; "
            "falling back to global"
        )
        return prior_df, summarize_geography_filter_result(
            prior_table_name="",
            filter_level_used="global",
            row_count_before=before,
            row_count_after=before,
            notes=note,
        )

    # 2) Otherwise use CBSA where available.
    if cbsa_cols and cbsa_values:
        filtered = _filter_by_columns(prior_df, cbsa_cols, cbsa_values)
        if not filtered.empty:
            note = f"CBSA filtering applied using columns={cbsa_cols} values={cbsa_values}"
            return filtered, summarize_geography_filter_result(
                prior_table_name="",
                filter_level_used="cbsa",
                row_count_before=before,
                row_count_after=len(filtered),
                notes=note,
            )
        note = (
            f"CBSA columns found ({cbsa_cols}) but no matching rows for {cbsa_values}; "
            "falling back to global"
        )
        return prior_df, summarize_geography_filter_result(
            prior_table_name="",
            filter_level_used="global",
            row_count_before=before,
            row_count_after=before,
            notes=note,
        )

    missing_note = "no county/PUMA/CBSA geography columns found in this prior table; using global/unfiltered"
    if county_cols and not county_values:
        missing_note = "county columns exist but GeographyContext has no county value; using global"
    elif puma_cols and not puma_values:
        missing_note = "PUMA columns exist but GeographyContext has no PUMA value; using global"
    elif cbsa_cols and not cbsa_values:
        missing_note = "CBSA columns exist but GeographyContext has no CBSA value; using global"

    return prior_df, summarize_geography_filter_result(
        prior_table_name="",
        filter_level_used="global",
        row_count_before=before,
        row_count_after=before,
        notes=missing_note,
    )


def apply_geography_context_to_priors(
    geography_context: GeographyContext,
    priors: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Apply best-effort geography filtering to all prior tables.

    Returns:
        (filtered_priors, per_table_debug_summary)
    """
    filtered_priors: dict[str, pd.DataFrame] = {}
    summaries: list[dict] = []

    for table_name, prior_df in priors.items():
        filtered_df, summary = filter_prior_table_by_geography(prior_df, geography_context)
        summary["prior_table_name"] = table_name
        filtered_priors[table_name] = filtered_df
        summaries.append(summary)

    return filtered_priors, summaries


def _filter_by_columns(df: pd.DataFrame, columns: list[str], values: list[str]) -> pd.DataFrame:
    values_normalized = {_normalize_text(v) for v in values if v}
    if not values_normalized:
        return df

    mask = pd.Series(False, index=df.index)
    for col in columns:
        series = df[col].astype(str).map(_normalize_text)
        mask = mask | series.isin(values_normalized)
    return df[mask]


def _candidate_values(*values: Optional[str]) -> list[str]:
    unique: list[str] = []
    seen = set()
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique


def _normalize_text(value: str) -> str:
    text = str(value).strip().strip("'\"").lower()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        text = text.lstrip("0") or "0"
    return text
