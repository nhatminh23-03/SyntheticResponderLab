"""Simple HUD ZIP lookup smoke test.

Usage:
	PYTHONPATH="$(pwd)" .venv-1/bin/python scripts/test_hud_zip_lookup.py 94103
	PYTHONPATH="$(pwd)" .venv-1/bin/python scripts/test_hud_zip_lookup.py
"""

from __future__ import annotations

import sys

from backend.data_sources.hud_zip_api import (
	HUDLookupError,
	lookup_zip_to_cbsa,
	lookup_zip_to_county,
	lookup_zip_to_tract,
)


def _read_zip_from_cli_or_prompt() -> str:
	if len(sys.argv) > 1 and sys.argv[1].strip():
		return sys.argv[1].strip()
	return input("Enter a ZIP code (5 digits): ").strip()


def main() -> int:
	zip_code = _read_zip_from_cli_or_prompt()
	if not zip_code:
		print("ERROR: ZIP code is required.")
		return 2

	print(f"\nHUD ZIP lookup for: {zip_code}\n")
	try:
		county = lookup_zip_to_county(zip_code)
		cbsa = lookup_zip_to_cbsa(zip_code)
		tract = lookup_zip_to_tract(zip_code)
	except HUDLookupError as exc:
		print("Lookup failed gracefully.")
		print(f"Reason: {exc}")
		print("Tip: Ensure HUD_API_TOKEN is set in your environment or .env.")
		return 1

	print("County mapping")
	print(f"  county_fips: {county.get('county_fips')}")
	print(f"  county_name: {county.get('county_name')}")
	print()

	print("CBSA mapping")
	print(f"  cbsa_code:   {cbsa.get('cbsa_code')}")
	print(f"  cbsa_name:   {cbsa.get('cbsa_name')}")
	print()

	print("Tract mapping")
	print(f"  tract:       {tract.get('tract')}")
	print()

	print("Done.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
