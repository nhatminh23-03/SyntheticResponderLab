"""Build lightweight grounding feature tables from normalized ACS/AHS parquet files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def bucket_income(series: pd.Series) -> pd.Series:
    """Map income values to simple buckets."""
    numeric = pd.to_numeric(series, errors="coerce")
    bucketed = pd.Series("unknown", index=series.index, dtype="string")
    bucketed.loc[numeric.between(0, 34999, inclusive="both")] = "low"
    bucketed.loc[numeric.between(35000, 74999, inclusive="both")] = "middle"
    bucketed.loc[numeric.between(75000, 149999, inclusive="both")] = "upper_middle"
    bucketed.loc[numeric >= 150000] = "high"
    return bucketed


def bucket_household_size(series: pd.Series) -> pd.Series:
    """Map household size to simple buckets."""
    numeric = pd.to_numeric(series, errors="coerce")
    bucketed = pd.Series("unknown", index=series.index, dtype="string")
    bucketed.loc[numeric == 1] = "1"
    bucketed.loc[numeric == 2] = "2"
    bucketed.loc[numeric.between(3, 4, inclusive="both")] = "3_4"
    bucketed.loc[numeric >= 5] = "5_plus"
    return bucketed


def write_feature_summary(path: Path, dataset_label: str, source_path: Path, df: pd.DataFrame) -> None:
    """Write simple metadata summary for one feature file."""
    summary: dict[str, Any] = {
        "dataset": dataset_label,
        "source_path": str(source_path),
        "output_path": str(path),
        "rows": int(len(df)),
        "columns": df.columns.tolist(),
        "preview_counts": {
            column: df[column].value_counts(dropna=False).head(10).to_dict()
            for column in df.columns
            if df[column].dtype == "object" or str(df[column].dtype).startswith("string")
        },
        "notes": "Lightweight derived grounding features only. No priors/persona integration yet.",
    }
    metadata_path = path.parents[1] / "metadata" / f"{path.stem}_summary.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{dataset_label}] Wrote feature summary: {metadata_path}")


def build_acs_person_features(source_path: Path, output_path: Path) -> pd.DataFrame:
    """Derive simple person-level ACS grounding features."""
    df = pd.read_parquet(source_path)

    required = {"age", "employment_status_code", "commute_mode_code", "personal_income", "wage_income"}
    missing = required.difference(set(df.columns))
    if missing:
        print(f"[ACS person features] Missing optional columns: {sorted(missing)}")

    out = pd.DataFrame(index=df.index)
    out["serialno"] = df["serialno"] if "serialno" in df.columns else pd.NA
    out["person_order"] = df["person_order"] if "person_order" in df.columns else pd.NA

    if "age" in df.columns:
        age_numeric = pd.to_numeric(df["age"], errors="coerce")
        out["age_bucket"] = pd.cut(
            age_numeric,
            bins=[-1, 24, 34, 44, 54, 64, 200],
            labels=["18_24", "25_34", "35_44", "45_54", "55_64", "65_plus"],
        ).astype("string").fillna("unknown")
    else:
        out["age_bucket"] = "unknown"

    income_base = (
        df["personal_income"]
        if "personal_income" in df.columns
        else (df["wage_income"] if "wage_income" in df.columns else pd.Series(pd.NA, index=df.index))
    )
    out["income_bucket"] = bucket_income(income_base)

    employment = pd.to_numeric(df["employment_status_code"], errors="coerce") if "employment_status_code" in df.columns else pd.Series(pd.NA, index=df.index)
    commute = pd.to_numeric(df["commute_mode_code"], errors="coerce") if "commute_mode_code" in df.columns else pd.Series(pd.NA, index=df.index)

    is_working = employment.isin([1, 2, 4, 5])
    out["is_working"] = is_working.fillna(False)

    work_mode = pd.Series("not_working_or_unknown", index=df.index, dtype="string")
    work_mode.loc[is_working & commute.eq(11)] = "remote_friendly"
    work_mode.loc[is_working & ~commute.eq(11)] = "commute_based"
    out["work_mode_hint"] = work_mode

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)
    print(f"[ACS person features] Wrote: {output_path}")
    return out


def build_acs_housing_features(source_path: Path, output_path: Path) -> pd.DataFrame:
    """Derive simple housing-level ACS grounding features."""
    df = pd.read_parquet(source_path)

    out = pd.DataFrame(index=df.index)
    out["serialno"] = df["serialno"] if "serialno" in df.columns else pd.NA
    out["puma"] = df["puma"] if "puma" in df.columns else pd.NA

    tenure = pd.to_numeric(df["tenure_code"], errors="coerce") if "tenure_code" in df.columns else pd.Series(pd.NA, index=df.index)
    ownership = pd.Series("unknown", index=df.index, dtype="string")
    ownership.loc[tenure.isin([1, 2])] = "owner"
    ownership.loc[tenure.eq(3)] = "renter"
    ownership.loc[tenure.notna() & ~tenure.isin([1, 2, 3])] = "other"
    out["ownership_group"] = ownership

    bld = pd.to_numeric(df["building_type_code"], errors="coerce") if "building_type_code" in df.columns else pd.Series(pd.NA, index=df.index)
    home_type = pd.Series("unknown", index=df.index, dtype="string")
    home_type.loc[bld.isin([1, 2])] = "single_family_like"
    home_type.loc[bld.isin([3, 4, 5, 6, 7, 8, 9])] = "multifamily_like"
    home_type.loc[bld.isin([10])] = "mobile_or_other"
    out["home_type_group"] = home_type

    out["household_size_bucket"] = bucket_household_size(df["num_people"] if "num_people" in df.columns else pd.Series(pd.NA, index=df.index))
    out["income_bucket"] = bucket_income(df["household_income"] if "household_income" in df.columns else pd.Series(pd.NA, index=df.index))

    rooms = pd.to_numeric(df["rooms"], errors="coerce") if "rooms" in df.columns else pd.Series(pd.NA, index=df.index)
    room_bucket = pd.Series("unknown", index=df.index, dtype="string")
    room_bucket.loc[rooms.between(0, 3, inclusive="both")] = "small"
    room_bucket.loc[rooms.between(4, 6, inclusive="both")] = "medium"
    room_bucket.loc[rooms >= 7] = "large"
    out["room_count_bucket"] = room_bucket

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)
    print(f"[ACS housing features] Wrote: {output_path}")
    return out


def build_ahs_features(source_path: Path, output_path: Path) -> pd.DataFrame:
    """Derive simple housing-level AHS grounding features."""
    df = pd.read_parquet(source_path)

    out = pd.DataFrame(index=df.index)
    out["control_id"] = df["control_id"] if "control_id" in df.columns else pd.NA
    out["cbsa_code"] = df["cbsa_code"] if "cbsa_code" in df.columns else pd.NA

    tenure = pd.to_numeric(df["tenure_code"], errors="coerce") if "tenure_code" in df.columns else pd.Series(pd.NA, index=df.index)
    ownership = pd.Series("unknown", index=df.index, dtype="string")
    ownership.loc[tenure.eq(1)] = "owner"
    ownership.loc[tenure.eq(2)] = "renter"
    ownership.loc[tenure.notna() & ~tenure.isin([1, 2])] = "other"
    out["ownership_group"] = ownership

    unit_size = pd.to_numeric(df["unit_size_code"], errors="coerce") if "unit_size_code" in df.columns else pd.Series(pd.NA, index=df.index)
    unit_size_group = pd.Series("unknown", index=df.index, dtype="string")
    unit_size_group.loc[unit_size.between(0, 2, inclusive="both")] = "small"
    unit_size_group.loc[unit_size.between(3, 4, inclusive="both")] = "medium"
    unit_size_group.loc[unit_size >= 5] = "large"
    out["unit_size_group"] = unit_size_group

    out["household_size_bucket"] = bucket_household_size(df["num_people"] if "num_people" in df.columns else pd.Series(pd.NA, index=df.index))
    out["income_bucket"] = bucket_income(df["household_income"] if "household_income" in df.columns else pd.Series(pd.NA, index=df.index))

    rent = pd.to_numeric(df["rent"], errors="coerce") if "rent" in df.columns else pd.Series(pd.NA, index=df.index)
    rent_bucket = pd.Series("unknown", index=df.index, dtype="string")
    rent_bucket.loc[rent.between(0, 999, inclusive="both")] = "low"
    rent_bucket.loc[rent.between(1000, 1999, inclusive="both")] = "middle"
    rent_bucket.loc[rent >= 2000] = "high"
    out["rent_bucket"] = rent_bucket

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)
    print(f"[AHS features] Wrote: {output_path}")
    return out


def main() -> None:
    """Build ACS/AHS feature tables and metadata summaries."""
    project_root = Path(__file__).resolve().parents[1]
    lookups_dir = project_root / "data" / "processed" / "lookups"

    acs_person_source = lookups_dir / "acs_person_normalized.parquet"
    acs_housing_source = lookups_dir / "acs_housing_normalized.parquet"
    ahs_source = lookups_dir / "ahs_normalized.parquet"

    for path in [acs_person_source, acs_housing_source, ahs_source]:
        if not path.exists():
            raise FileNotFoundError(f"Missing normalized input: {path}")

    acs_person_features_path = lookups_dir / "acs_person_features.parquet"
    acs_housing_features_path = lookups_dir / "acs_housing_features.parquet"
    ahs_features_path = lookups_dir / "ahs_features.parquet"

    acs_person_df = build_acs_person_features(acs_person_source, acs_person_features_path)
    acs_housing_df = build_acs_housing_features(acs_housing_source, acs_housing_features_path)
    ahs_df = build_ahs_features(ahs_source, ahs_features_path)

    write_feature_summary(acs_person_features_path, "ACS person features", acs_person_source, acs_person_df)
    write_feature_summary(acs_housing_features_path, "ACS housing features", acs_housing_source, acs_housing_df)
    write_feature_summary(ahs_features_path, "AHS features", ahs_source, ahs_df)


if __name__ == "__main__":
    main()
