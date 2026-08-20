"""Build and print normalized GeographyContext from ZIP.

Usage:
    PYTHONPATH="$(pwd)" .venv-1/bin/python scripts/test_geography_context.py 94103
    PYTHONPATH="$(pwd)" .venv-1/bin/python scripts/test_geography_context.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.grounding.geography_context import build_geography_context_from_zip


def _read_zip_from_cli_or_prompt() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    return input("Enter a ZIP code (5 digits): ").strip()


def main() -> int:
    zip_code = _read_zip_from_cli_or_prompt()
    if not zip_code:
        print("ERROR: ZIP code is required.")
        return 2

    project_root = Path(__file__).resolve().parents[1]
    puma_lookup_path = project_root / "data" / "processed" / "lookups" / "hud_zip_puma_lookup.parquet"

    print(f"\nBuilding geography context for ZIP: {zip_code} (local-first mode)\n")
    print(f"Local ZIP->PUMA lookup exists: {puma_lookup_path.exists()}")
    context = build_geography_context_from_zip(zip_code=zip_code, prefer_local=True)

    print("GeographyContext")
    print(f"  zip_code:    {context.zip_code}")
    print(f"  county_fips: {context.county_fips}")
    print(f"  county_name: {context.county_name}")
    print(f"  cbsa_code:   {context.cbsa_code}")
    print(f"  cbsa_name:   {context.cbsa_name}")
    print(f"  puma:        {context.puma}")
    print(f"  tract_code:  {context.tract_code}")
    print(f"  source:      {context.source}")
    if context.source != "hud_local_crosswalk":
        print("\nNote: Local enrichment was not fully matched; context is using a fallback source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
