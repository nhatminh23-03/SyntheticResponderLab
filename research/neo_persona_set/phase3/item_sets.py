"""Named sets of survey items to score, and the items set aside from scoring.

Dr. Lin's calibration / validation split (report of 2026-09-26, section 1): anything fitted on one
group of items is scored on the other, so no result is graded on the items it was tuned on.

- Validation (13): category interest, purchase interest, 24-month likelihood and the ten concept
  items. These map one-to-one onto our ids.
- Calibration: his 13 are the 7 barriers, 5 value drivers and sponsorship. Our survey carries only
  3 of the 5 value drivers (the AYTM rows Smart Technology and Showroom have no synthetic
  counterpart) and Q15 is set aside, so on our survey the calibration set has 10 items.

Both lists were checked against his item_split.csv (registered 2026-09-20, shared 2026-09-30):
LIN_ITEM_NAMES translates his names (Q5_cost .. Q5_resale, Q9a ..) to ours. His calibration list
also carries Q15, which stays out here because Dr. Wang set it aside. The four driver questions
(LIN_DRIVERS) are never scored: in a hybrid run their answers are copied from real respondents.

An item set is either one of NAMED_SETS or a file with one of our question ids per line ('#' starts
a comment). compare_real.py --items takes either.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import crosswalk  # noqa: E402

# Items left out of every named set, with the decision behind each.
SET_ASIDE: Dict[str, str] = {
    "Q15": "set aside by Dr. Wang 2026-09-24: its answer depends more on the model than on the respondents",
    "Q24": "left out by Dr. Wang 2026-09-24: no persona field carries HOA status and ACS PUMS has no HOA variable",
}

LIN_VALIDATION: List[str] = ["Q0B", "Q1", "Q2", "Q9A", "Q9B", "Q10A", "Q10B", "Q11A", "Q11B", "Q12A", "Q12B", "Q13A", "Q13B"]
LIN_CALIBRATION: List[str] = ["Q5_1", "Q5_2", "Q5_3", "Q5_4", "Q5_5", "Q5_6", "Q5_7", "Q16", "Q17", "Q19"]

# His item names -> ours. The barrier rows follow crosswalk.BARRIER_ROWS (cost, HOA, permit, space,
# financing, quality, resale); the concept items differ only in case.
LIN_ITEM_NAMES: Dict[str, str] = {
    **dict(zip(["Q5_cost", "Q5_hoa", "Q5_permit", "Q5_space", "Q5_financing", "Q5_quality", "Q5_resale"],
               [f"Q5_{index}" for index in range(1, 8)])),
    "Q0b": "Q0B", "Q1": "Q1", "Q2": "Q2", "Q9a": "Q9A", "Q9b": "Q9B", "Q10a": "Q10A", "Q10b": "Q10B",
    "Q11a": "Q11A", "Q11b": "Q11B", "Q12a": "Q12A", "Q12b": "Q12B", "Q13a": "Q13A", "Q13b": "Q13B",
    "Q15": "Q15", "Q16": "Q16", "Q17": "Q17", "Q19": "Q19",
}
# Value-driver rows Smart Technology and Showroom: in his list, not on our survey.
LIN_NOT_ON_OUR_SURVEY = {"Q17b", "Q17c"}
# Prior consideration, primary use, outdoor recreation, club membership.
LIN_DRIVERS: List[str] = ["Q0A", "Q3", "Q25", "Q26"]


def _all_scored() -> List[str]:
    return [q.our_id for q in crosswalk.CROSSWALK if q.kind != "none" and q.scored and q.our_id not in SET_ASIDE]


NAMED_SETS: Dict[str, List[str]] = {
    "lin13-validation": LIN_VALIDATION,
    "lin13-calibration": LIN_CALIBRATION,
    "all-scored": _all_scored(),
}


def check_items(ids: List[str], source: str) -> List[str]:
    """Raise ValueError unless every id is a scorable item that has not been set aside."""
    if not ids:
        raise ValueError(f"{source}: no items")
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"{source}: duplicate items {duplicates}")
    for item in ids:
        qmap = crosswalk.BY_OUR_ID.get(item)
        if qmap is None:
            raise ValueError(f"{source}: {item} is not a survey item")
        if qmap.kind == "none":
            raise ValueError(f"{source}: {item} has no counterpart in the real survey")
        if not qmap.scored:
            raise ValueError(f"{source}: {item} is report-only and never scored")
        if item in SET_ASIDE:
            raise ValueError(f"{source}: {item} is set aside ({SET_ASIDE[item]})")
    return ids


def load_item_set(spec: str) -> Tuple[str, List[str]]:
    """(name, ids) for a named set or an item file."""
    if spec in NAMED_SETS:
        return spec, list(NAMED_SETS[spec])
    path = Path(spec).expanduser()
    if not path.is_file():
        raise ValueError(f"{spec!r} is neither a named set ({', '.join(NAMED_SETS)}) nor a file")
    ids: List[str] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    return path.name, check_items(ids, str(path))


# The named sets are checked at import so a later crosswalk change cannot silently break them.
for _name, _ids in NAMED_SETS.items():
    check_items(_ids, f"named set {_name}")
