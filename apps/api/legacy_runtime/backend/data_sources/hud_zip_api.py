"""Minimal HUD ZIP crosswalk client (setup stage only).

This module is intentionally lightweight:
- token from env (`HUD_API_TOKEN`) or explicit parameter,
- ZIP lookup helpers for county / CBSA / tract,
- no persona or simulation wiring.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HUD_DEFAULT_BASE_URL = "https://www.huduser.gov/hudapi/public"


class HUDLookupError(RuntimeError):
	"""Raised when HUD ZIP lookup fails or returns unusable payload."""


@dataclass(frozen=True)
class HUDGeoMapping:
	"""Normalized geography crosswalk mapping for one ZIP lookup."""

	zip_code: str
	county_fips: Optional[str]
	county_name: Optional[str]
	cbsa_code: Optional[str]
	cbsa_name: Optional[str]
	tract: Optional[str]
	raw: Dict[str, Any]


def get_hud_token(token: Optional[str] = None) -> str:
	"""Return HUD API token from argument or environment."""
	resolved = (token or os.getenv("HUD_API_TOKEN", "")).strip()
	if not resolved:
		raise HUDLookupError(
			"HUD API token is missing. Set HUD_API_TOKEN in your environment or pass token explicitly."
		)
	return resolved


def lookup_zip_to_county(zip_code: str, token: Optional[str] = None) -> Dict[str, Optional[str]]:
	"""Lookup ZIP -> county mapping via HUD API."""
	mapping = lookup_zip_geography(zip_code=zip_code, token=token)
	return {
		"zip_code": mapping.zip_code,
		"county_fips": mapping.county_fips,
		"county_name": mapping.county_name,
	}


def lookup_zip_to_cbsa(zip_code: str, token: Optional[str] = None) -> Dict[str, Optional[str]]:
	"""Lookup ZIP -> CBSA mapping via HUD API."""
	mapping = lookup_zip_geography(zip_code=zip_code, token=token)
	return {
		"zip_code": mapping.zip_code,
		"cbsa_code": mapping.cbsa_code,
		"cbsa_name": mapping.cbsa_name,
	}


def lookup_zip_to_tract(zip_code: str, token: Optional[str] = None) -> Dict[str, Optional[str]]:
	"""Lookup ZIP -> tract mapping via HUD API (if field exists in response)."""
	mapping = lookup_zip_geography(zip_code=zip_code, token=token)
	return {
		"zip_code": mapping.zip_code,
		"tract": mapping.tract,
	}


def lookup_zip_geography(zip_code: str, token: Optional[str] = None) -> HUDGeoMapping:
	"""Return normalized HUD geography mapping for a ZIP code.

	This function is defensive on response shape because HUD endpoints can vary.
	"""
	zip_clean = _normalize_zip(zip_code)
	if not zip_clean:
		raise HUDLookupError(f"Invalid ZIP code input: {zip_code!r}")

	payload = _fetch_hud_zip_payload(zip_clean, token=get_hud_token(token))
	row = _extract_first_mapping_row(payload)
	if not row:
		raise HUDLookupError(
			f"HUD API returned no usable mapping row for ZIP {zip_clean}. Response keys: {list(payload.keys())}"
		)

	county_fips = _get_first_str(row, ["county_fips", "countyfips", "county_code", "countycode"])
	county_name = _get_first_str(row, ["county_name", "countyname", "county"])
	cbsa_code = _get_first_str(row, ["cbsa_code", "cbsacode", "cbsa"])
	cbsa_name = _get_first_str(row, ["cbsa_name", "cbsaname", "metro_name", "metroname"])
	tract = _get_first_str(row, ["tract", "tract_code", "tractcode", "census_tract", "fips_tract"])

	return HUDGeoMapping(
		zip_code=zip_clean,
		county_fips=county_fips,
		county_name=county_name,
		cbsa_code=cbsa_code,
		cbsa_name=cbsa_name,
		tract=tract,
		raw=row,
	)


def _fetch_hud_zip_payload(zip_code: str, token: str) -> Dict[str, Any]:
	"""Call likely HUD ZIP endpoints and return decoded JSON payload."""
	base_url = os.getenv("HUD_API_BASE_URL", HUD_DEFAULT_BASE_URL).rstrip("/")
	candidates = [
		(f"{base_url}/usps", {"query": zip_code}),
		(f"{base_url}/usps", {"zip": zip_code}),
		(f"{base_url}/zip", {"zip": zip_code}),
		(f"{base_url}/zip/{zip_code}", {}),
	]

	last_error: Optional[Exception] = None
	for endpoint, params in candidates:
		url = endpoint
		if params:
			url = f"{endpoint}?{urlencode(params)}"

		request = Request(
			url,
			headers={
				"Authorization": f"Bearer {token}",
				"accept": "application/json",
				"content-type": "application/json",
			},
			method="GET",
		)
		try:
			with urlopen(request, timeout=15) as response:
				body = response.read().decode("utf-8", errors="replace")
				data = json.loads(body)
				if isinstance(data, dict):
					return data
				last_error = HUDLookupError(f"Unexpected non-dict JSON payload type: {type(data).__name__}")
		except HTTPError as exc:
			last_error = HUDLookupError(f"HUD API HTTP error at {url}: {exc.code} {exc.reason}")
		except URLError as exc:
			last_error = HUDLookupError(f"HUD API network error at {url}: {exc.reason}")
		except json.JSONDecodeError:
			last_error = HUDLookupError(f"HUD API returned non-JSON payload at {url}")

	if last_error is None:
		last_error = HUDLookupError("HUD API request failed for unknown reason.")
	raise last_error


def _extract_first_mapping_row(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
	"""Extract the first mapping-like row from flexible HUD payload shapes."""

	if any(key in payload for key in ("county", "county_name", "cbsa", "tract", "county_fips", "cbsa_code")):
		return payload

	for key in ("data", "results", "result", "response"):
		value = payload.get(key)
		row = _extract_row_from_any(value)
		if row:
			return row

	for value in payload.values():
		row = _extract_row_from_any(value)
		if row:
			return row

	return None


def _extract_row_from_any(value: Any) -> Optional[Dict[str, Any]]:
	if isinstance(value, dict):
		if any(key in value for key in ("county", "county_name", "cbsa", "tract", "county_fips", "cbsa_code")):
			return value
		for nested in value.values():
			row = _extract_row_from_any(nested)
			if row:
				return row
		return None
	if isinstance(value, list):
		for item in value:
			row = _extract_row_from_any(item)
			if row:
				return row
	return None


def _get_first_str(row: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
	"""Get first non-empty string value from row by candidate keys."""
	lower_map = {str(k).lower(): v for k, v in row.items()}
	for key in keys:
		value = lower_map.get(key.lower())
		if value is None:
			continue
		text = str(value).strip()
		if text and text.lower() not in {"none", "null", "nan"}:
			return text
	return None


def _normalize_zip(zip_code: str) -> str:
	"""Normalize zip input to 5-digit ZIP where possible."""
	text = (zip_code or "").strip()
	if "-" in text:
		text = text.split("-", 1)[0]
	digits = "".join(ch for ch in text if ch.isdigit())
	if len(digits) >= 5:
		return digits[:5]
	return ""
