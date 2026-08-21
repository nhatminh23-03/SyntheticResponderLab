"""Test best-effort geography-to-prior filtering adapter.

Usage:
    PYTHONPATH="$(pwd)" .venv-1/bin/python scripts/test_geography_prior_filter.py 94103
    PYTHONPATH="$(pwd)" .venv-1/bin/python scripts/test_geography_prior_filter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from backend.grounding.geography_context import build_geography_context_from_zip
from backend.grounding.geography_prior_filter import apply_geography_context_to_priors
from backend.grounding.prior_sampler import load_grounding_priors


def _read_zip_from_cli_or_prompt() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    return input("Enter a ZIP code (5 digits): ").strip()


def main() -> int:
    zip_code = _read_zip_from_cli_or_prompt()
    if not zip_code:
        print("ERROR: ZIP code is required.")
        return 2

    print(f"\nApplying geography prior filter for ZIP: {zip_code}\n")

    project_root = Path(__file__).resolve().parents[1]
    puma_lookup_path = project_root / "data" / "processed" / "lookups" / "hud_zip_puma_lookup.parquet"
    print(f"Local ZIP->PUMA lookup exists: {puma_lookup_path.exists()}")

    geography_context = build_geography_context_from_zip(zip_code=zip_code, prefer_local=True)
    print(f"GeographyContext source: {geography_context.source}")

    print("\nGeographyContext")
    print(f"  zip_code:    {geography_context.zip_code}")
    print(f"  county_fips: {geography_context.county_fips}")
    print(f"  county_name: {geography_context.county_name}")
    print(f"  cbsa_code:   {geography_context.cbsa_code}")
    print(f"  cbsa_name:   {geography_context.cbsa_name}")
    print(f"  puma:        {geography_context.puma}")
    print(f"  tract_code:  {geography_context.tract_code}")
    print(f"  source:      {geography_context.source}")

    priors = _load_geo_aware_priors_if_available()
    filtered_priors, summaries = apply_geography_context_to_priors(geography_context, priors)

    print("\nPer-table filter summary")
    narrowed_count = 0
    for summary in summaries:
        table = summary["prior_table_name"]
        level = summary["filter_level_used"]
        before = summary["row_count_before"]
        after = summary["row_count_after"]
        narrowed = summary["narrowed"]
        notes = summary["notes"]
        if narrowed:
            narrowed_count += 1
        print(f"- {table}: level={level}, before={before}, after={after}, narrowed={narrowed}")
        print(f"  note: {notes}")

    print(
        f"\nResult: {narrowed_count}/{len(summaries)} prior tables narrowed by geography filtering."
    )

    if narrowed_count == 0:
        print(
            "No narrowing detected. This is expected when prior tables lack matchable geo columns or GeographyContext lacks matchable geo values."
        )

    print("\nDone.")
    return 0


def _load_geo_aware_priors_if_available() -> dict[str, pd.DataFrame]:
    """Load geo-aware priors when present; otherwise fall back to baseline priors."""
    project_root = Path(__file__).resolve().parents[1]
    priors_dir = project_root / "data" / "processed" / "priors"

    geo_paths = {
        "age_income": priors_dir / "age_income_priors_geo.parquet",
        "ownership_home_type": priors_dir / "ownership_home_type_priors_geo.parquet",
        "household_size": priors_dir / "household_size_priors_geo.parquet",
        "work_mode": priors_dir / "work_mode_hints_geo.parquet",
    }

    if all(path.exists() for path in geo_paths.values()):
        print("\nUsing geo-aware prior tables.")
        loaded: dict[str, pd.DataFrame] = {
            key: pd.read_parquet(path)
            for key, path in geo_paths.items()
        }

        # Keep optional CEX tables from default prior loader if present.
        base_priors = load_grounding_priors()
        for optional_key in ["cex_affordability", "cex_spending"]:
            if optional_key in base_priors:
                loaded[optional_key] = base_priors[optional_key]

        return loaded

    print("\nGeo-aware priors not fully available; falling back to baseline priors.")
    print("Tip: run scripts/build_grounding_features_geo.py and scripts/build_grounding_priors_geo.py first.")
    return load_grounding_priors()


if __name__ == "__main__":
    raise SystemExit(main())
