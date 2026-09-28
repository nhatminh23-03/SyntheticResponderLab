"""Read the AYTM raw export (the withheld real survey) into canonical columns. Read-only.

This is the only phase-3 module that opens the real file, and only when a caller passes the path
explicitly: there is no default path. Nothing in phase 2 imports it (test_realdata.py checks that).

Export layout: row 1 holds the question text (blank on continuation columns of a matrix or
multi-select block), row 2 the row/option label (blank on simple columns), rows 3.. one respondent
each. Canonical keys forward-fill row 1, keep only the question code, and append the short row-2
label: "Q9|The total cost (~$23,000)", "Q33|A4", "Q8|OE", "Q33|A11|OE", "Gender".
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

CODE_PATTERN = re.compile(r"^(PQ\d+|Q\d+)((?:\.[A-Za-z0-9]+)*)$")
OPTION_COLUMN = re.compile(r"^A\d+$")
_LEADING_INT = re.compile(r"^\s*(\d+)")
_SUB_LABEL_CUT = re.compile(r"^(.*?)\s*:\s")
_DASHES = re.compile("[‐‑‒–—―−]")
_SPACES = re.compile(r"\s+")

REAL_DATA_MARKERS = ("aytm", "survey-760085", "raw 600-participant", "tony visit")


class RealDataPathError(SystemExit):
    def __init__(self, message: str) -> None:
        super().__init__(3)
        self.message = message


def assert_not_real_data_path(path: Path, label: str) -> Path:
    """Refuse (exit 3) any output or run path whose name points at the real-respondent material."""
    resolved = Path(path).expanduser().resolve()
    lowered = str(resolved).lower()
    for marker in REAL_DATA_MARKERS:
        if marker in lowered:
            print(f"REFUSED: {label} path {resolved} names the real-respondent material ({marker!r}).", file=sys.stderr)
            raise RealDataPathError(f"{label} path names real data: {resolved}")
    return resolved


def assert_outside_real_folder(path: Path, real_path: Path, label: str) -> Path:
    """Refuse a path inside the folder holding the real file, whatever that folder is called."""
    resolved = assert_not_real_data_path(path, label)
    real_dir = Path(real_path).expanduser().resolve().parent
    if resolved == real_dir or real_dir in resolved.parents:
        print(f"REFUSED: {label} path {resolved} is inside the real-data folder {real_dir}.", file=sys.stderr)
        raise RealDataPathError(f"{label} path is inside the real-data folder: {resolved}")
    return resolved


def split_code(header_text: str) -> Optional[Tuple[str, List[str]]]:
    """'Q33.A4: Which outreach ...' -> ('Q33', ['A4']); 'Q8.OE' -> ('Q8', ['OE']); 'Gender' -> None."""
    head = header_text.split(": ", 1)[0].strip()
    match = CODE_PATTERN.match(head)
    if match is None:
        return None
    return match.group(1), [part for part in match.group(2).split(".") if part]


def short_sub_label(row2_text: str) -> str:
    """Row-2 label without the repeated question text: 'HOA rules : Below is ...' -> 'HOA rules'."""
    text = row2_text.strip()
    match = _SUB_LABEL_CUT.match(text)
    return match.group(1).strip() if match else text


def canonical_key(row1_filled: str, row2_text: str) -> str:
    code = split_code(row1_filled)
    parts = [code[0], *code[1]] if code else [row1_filled.strip()]
    sub = short_sub_label(row2_text)
    if sub:
        parts.append(sub)
    return "|".join(parts)


def forward_fill(values: List[str]) -> List[str]:
    filled: List[str] = []
    last = ""
    for value in values:
        if value.strip():
            last = value.strip()
        filled.append(last)
    return filled


def normalize_key(text: str) -> str:
    return _SPACES.sub(" ", _DASHES.sub("-", text)).strip().casefold()


def build_columns(row1: List[str], row2: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """Canonical keys (unique, in file order) and key -> full row-1 text."""
    keys: List[str] = []
    header_text: Dict[str, str] = {}
    seen: Counter = Counter()
    for filled, sub in zip(forward_fill(row1), row2):
        key = canonical_key(filled, sub)
        seen[key] += 1
        if seen[key] > 1:
            key = f"{key}#{seen[key]}"
        keys.append(key)
        header_text[key] = filled
    return keys, header_text


def base_code(key: str) -> str:
    return key.split("|", 1)[0]


@dataclass
class RealSurvey:
    path: str
    columns: List[str]
    header_text: Dict[str, str]
    rows: List[Dict[str, str]]
    _index: Dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._index = {normalize_key(column): column for column in self.columns}

    @property
    def n(self) -> int:
        return len(self.rows)

    def find(self, key: str) -> Optional[str]:
        return self._index.get(normalize_key(key))

    def col(self, key_prefix: str) -> List[str]:
        wanted = normalize_key(key_prefix)
        return [c for c in self.columns if normalize_key(c) == wanted or normalize_key(c).startswith(wanted + "|")]

    def values(self, key: str) -> List[str]:
        column = self.find(key)
        if column is None:
            raise KeyError(key)
        return [row[column] for row in self.rows]

    def base_codes(self) -> List[str]:
        ordered: List[str] = []
        for column in self.columns:
            code = base_code(column)
            if code not in ordered:
                ordered.append(code)
        return ordered


def load_real_survey(path: Path) -> RealSurvey:
    """Parse the two-header export; rows are dicts keyed by canonical column key."""
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            row1 = next(reader)
            row2 = next(reader)
        except StopIteration:
            raise ValueError(f"{path}: expected two header rows")
        if not any(split_code(cell) for cell in row1):
            raise ValueError(f"{path}: no question codes (PQ1, Q1, ...) in the first header row")
        columns, header_text = build_columns(row1, row2)
        rows: List[Dict[str, str]] = []
        for record in reader:
            if not any(cell.strip() for cell in record):
                continue
            padded = list(record[: len(columns)]) + [""] * (len(columns) - len(record))
            rows.append(dict(zip(columns, padded)))
    return RealSurvey(path=str(path), columns=columns, header_text=header_text, rows=rows)


RESPONSE_ID_KEY = "Response ID"


def read_id_file(path: Path) -> List[str]:
    """One id per line; blank lines and '#' comments are skipped; duplicates are an error."""
    ids: List[str] = []
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate ids {duplicates[:5]}")
    if not ids:
        raise ValueError(f"{path}: no ids")
    return ids


def subset_by_response_id(real: RealSurvey, ids: List[str]) -> RealSurvey:
    """A copy of the survey holding only the respondents whose Response ID is listed."""
    column = real.find(RESPONSE_ID_KEY)
    if column is None:
        raise ValueError(f"{real.path}: no {RESPONSE_ID_KEY!r} column")
    present = {row[column].strip() for row in real.rows}
    missing = [item for item in ids if item not in present]
    if missing:
        raise ValueError(f"{len(missing)} ids are not in the real file, e.g. {missing[:5]}")
    wanted = set(ids)
    rows = [row for row in real.rows if row[column].strip() in wanted]
    return RealSurvey(path=real.path, columns=list(real.columns), header_text=dict(real.header_text), rows=rows)


def likert_label_to_int(cell: Optional[str]) -> Optional[int]:
    """'1 - Not interested' -> 1, '3' -> 3, '' or 'N/A' -> None."""
    if cell is None:
        return None
    match = _LEADING_INT.match(str(cell))
    return int(match.group(1)) if match else None


def is_option_column(key: str, prefix: str) -> bool:
    parts = key.split("|")
    return len(parts) == 2 and normalize_key(parts[0]) == normalize_key(prefix) and bool(OPTION_COLUMN.match(parts[1]))


def multiselect_columns(columns: List[str], prefix: str) -> List[str]:
    return [column for column in columns if is_option_column(column, prefix)]


def multiselect_block(rows: List[Dict[str, str]], prefix: str) -> List[Set[str]]:
    """One set of selected option labels per respondent (a cell holds the label when selected, else '')."""
    columns = multiselect_columns(list(rows[0].keys()), prefix) if rows else []
    return [{row[column].strip() for column in columns if row.get(column, "").strip()} for row in rows]


def multiselect_sub_ids(rows: List[Dict[str, str]], prefix: str) -> List[Set[str]]:
    columns = multiselect_columns(list(rows[0].keys()), prefix) if rows else []
    return [{column.split("|")[1] for column in columns if row.get(column, "").strip()} for row in rows]
