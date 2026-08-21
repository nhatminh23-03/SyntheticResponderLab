"""Build geo-aware grounding feature tables from normalized ACS/AHS parquet files.

This is a setup-only extension that preserves available geography keys in feature tables.
No simulation or sampler integration is performed here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.build_grounding_features import (
    build_acs_housing_features,
    build_acs_person_features,
    build_ahs_features,
)


def _write_feature_summary(path: Path, dataset_label: str, source_path: Path, df: pd.DataFrame) -> None:
    summary: dict[str, Any] = {
        "dataset": dataset_label,
        "source_path": str(source_path),
        "output_path": str(path),
        "rows": int(len(df)),
        "columns": df.columns.tolist(),
        "geo_columns": [
            col for col in df.columns
            if any(token in col.lower() for token in ["puma", "cbsa", "state", "county", "tract", "zip"])
        ],
        "notes": "Geo-aware feature table preserving existing geography keys only.",
    }
    metadata_path = path.parents[1] / "metadata" / f"{path.stem}_summary.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{dataset_label}] Wrote feature summary: {metadata_path}")


def _copy_geo_columns(normalized_df: pd.DataFrame, feature_df: pd.DataFrame, candidate_cols: list[str]) -> pd.DataFrame:
    out = feature_df.copy()
    for col in candidate_cols:
        if col in normalized_df.columns and col not in out.columns:
            out[col] = normalized_df[col]
    return out


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    lookups_dir = project_root / "data" / "processed" / "lookups"

    acs_person_source = lookups_dir / "acs_person_normalized.parquet"
    acs_housing_source = lookups_dir / "acs_housing_normalized.parquet"
    ahs_source = lookups_dir / "ahs_normalized.parquet"

    for path in [acs_person_source, acs_housing_source, ahs_source]:
        if not path.exists():
            raise FileNotFoundError(f"Missing normalized input: {path}")

    acs_person_features_path = lookups_dir / "acs_person_features_geo.parquet"
    acs_housing_features_path = lookups_dir / "acs_housing_features_geo.parquet"
    ahs_features_path = lookups_dir / "ahs_features_geo.parquet"

    # Build baseline feature frames with existing transformation logic.
    acs_person_base = build_acs_person_features(acs_person_source, acs_person_features_path)
    acs_housing_base = build_acs_housing_features(acs_housing_source, acs_housing_features_path)
    ahs_base = build_ahs_features(ahs_source, ahs_features_path)

    # Re-open normalized sources to preserve existing geography keys when available.
    acs_person_norm = pd.read_parquet(acs_person_source)
    acs_housing_norm = pd.read_parquet(acs_housing_source)
    ahs_norm = pd.read_parquet(ahs_source)

    acs_person_geo = _copy_geo_columns(acs_person_norm, acs_person_base, ["puma", "state"])
    acs_housing_geo = _copy_geo_columns(acs_housing_norm, acs_housing_base, ["puma", "state"])
    ahs_geo = _copy_geo_columns(ahs_norm, ahs_base, ["cbsa_code", "state"])

    acs_person_geo.to_parquet(acs_person_features_path, index=False)
    acs_housing_geo.to_parquet(acs_housing_features_path, index=False)
    ahs_geo.to_parquet(ahs_features_path, index=False)

    print(f"[ACS person features geo] Wrote: {acs_person_features_path}")
    print(f"[ACS housing features geo] Wrote: {acs_housing_features_path}")
    print(f"[AHS features geo] Wrote: {ahs_features_path}")

    _write_feature_summary(acs_person_features_path, "ACS person features geo", acs_person_source, acs_person_geo)
    _write_feature_summary(acs_housing_features_path, "ACS housing features geo", acs_housing_source, acs_housing_geo)
    _write_feature_summary(ahs_features_path, "AHS features geo", ahs_source, ahs_geo)


if __name__ == "__main__":
    main()
