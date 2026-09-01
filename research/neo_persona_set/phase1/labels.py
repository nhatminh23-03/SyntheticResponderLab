"""Decode ACS PUMS numeric codes into readable text.

Labels are parsed from the official PUMS data dictionary at runtime rather than hardcoded, so
they cannot drift from the vintage actually being used. OCCP alone carries several hundred codes,
which would be unmaintainable by hand.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import requests

DICT_URL = "https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2024.txt"
CACHE = Path(__file__).resolve().parent.parent / "out" / "cache" / "dict2024.txt"

# A variable header line looks like:  SCHL        Character   2
_HEADER = re.compile(r"^([A-Z][A-Z0-9]{1,15})\s+(Character|Numeric)\s+\d+\s*$")
# A code line looks like:             01     .No schooling completed
_CODE = re.compile(r"^\s+(\S+)\s*\.(.*)$")


def _dictionary_text() -> str:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(DICT_URL, timeout=120)
        response.raise_for_status()
        CACHE.write_bytes(response.content)
    return CACHE.read_text(encoding="utf-8", errors="replace")


@lru_cache(maxsize=1)
def code_maps() -> dict[str, dict[str, str]]:
    """Return {variable: {code: label}} for every coded variable in the dictionary."""
    maps: dict[str, dict[str, str]] = {}
    current: str | None = None

    for line in _dictionary_text().splitlines():
        header = _HEADER.match(line)
        if header:
            current = header.group(1)
            maps.setdefault(current, {})
            continue
        if current is None:
            continue
        code = _CODE.match(line)
        if code:
            raw, label = code.group(1), code.group(2).strip()
            maps[current][raw.strip()] = label
        # Anything else inside a block (notably the variable's own description line, which is not
        # indented) is skipped. State resets only when the next header appears — resetting on any
        # unindented line would drop every code, since the description always precedes them.

    return maps


def decode(variable: str, value) -> str | None:
    """Decode one value, tolerating float/int/zero-padded string representations."""
    if value is None:
        return None
    mapping = code_maps().get(variable)
    if not mapping:
        return None

    candidates: list[str] = []
    text = str(value).strip()
    if text in {"", "nan", "None"}:
        return None
    candidates.append(text)

    # Parquet round-trips these as floats; the dictionary keys are zero-padded strings.
    try:
        number = int(float(text))
        candidates.extend([str(number), f"{number:02d}", f"{number:04d}"])
    except (TypeError, ValueError):
        pass

    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]
    return None


# Some codes are technically accurate but read badly inside a persona description.
EDUCATION_SIMPLE = {
    "Regular high school diploma": "high school diploma",
    "GED or alternative credential": "GED",
    "Some college, but less than 1 year": "some college",
    "1 or more years of college credit, no degree": "some college",
    "Associate's degree": "associate degree",
    "Bachelor's degree": "bachelor's degree",
    "Master's degree": "master's degree",
    "Professional degree beyond a bachelor's degree": "professional degree",
    "Doctorate degree": "doctorate",
}


def simplify_education(label: str | None) -> str | None:
    if not label:
        return None
    return EDUCATION_SIMPLE.get(label, label.lower())
