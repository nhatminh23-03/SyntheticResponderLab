"""Make a run-ready hybrid persona file from Dr. Lin's driver file and the team's persona file.

Her personas_S*_drv.csv carry the team's persona columns plus four driver answers copied from a
real respondent in the calibration half, and that respondent's row id (driver_donor_id, aytm_N).
This keeps every persona column from the team's own file and takes only the five driver columns
from hers, so a hybrid prompt differs from the synthetic one only by customer_facts. persona_id
stays in the team file's numbering, so the mixed-panel deal and the response-style assignment line
up with the synthetic baselines.

Nothing is written unless every check passes (exit 2 otherwise):
- each of her personas is in the team file, matched on --lin-id-column, with no duplicates;
- her copy of every persona column agrees with the team's (numbers compared as numbers);
- the four driver columns are filled;
- every donor is a row id in her split file, in the "cal" half.
The output names a real respondent per persona, so it is refused inside the repository and
inside the real-data folder.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/import_driver_personas.py \\
        --lin "../SyntheticResponderLab-Assets/DrLinSplit/Regenerated Persona Files/personas_S1_drv.csv" \\
        --lin-id-column team_s1_id \\
        --team ../SyntheticResponderLab-Assets/6_subset_of_dataset_plus_the_all_600_persona_data/phase1_interview_matched600_s1.csv \\
        --split ../SyntheticResponderLab-Assets/DrLinSplit/aytm_respondent_split_ids.csv \\
        --out ../SyntheticResponderLab-Assets/hybrid_personas/s1_drv.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import filter_qualified  # noqa: E402
import make_real_split  # noqa: E402
import realdata  # noqa: E402

# The runner reads these four (phase2/run_survey.py DRIVER_COLUMNS); the donor id never reaches a prompt.
DRIVER_COLUMNS = [
    "prior_consideration_of_backyard_unit",
    "outdoor_recreation_frequency",
    "member_of_outdoor_club",
    "most_likely_use_for_a_backyard_unit",
]
DONOR_COLUMN = "driver_donor_id"


def read_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def same_value(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def merge(lin: List[Dict[str, str]], team: List[Dict[str, str]], split: Dict[str, str], lin_id_column: str) -> List[Dict[str, str]]:
    """Team rows (team order, her personas only) plus her driver columns. Raises ValueError on any check."""
    if not lin:
        raise ValueError("the driver file is empty")
    missing_columns = [c for c in [lin_id_column, *DRIVER_COLUMNS, DONOR_COLUMN] if c not in lin[0]]
    if missing_columns:
        raise ValueError(f"the driver file lacks {missing_columns}")
    ids = [row[lin_id_column] for row in lin]
    duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
    if duplicates:
        raise ValueError(f"duplicate personas in the driver file: {duplicates[:5]}")
    by_id = {row["persona_id"]: row for row in team}
    unknown = [pid for pid in ids if pid not in by_id]
    if unknown:
        raise ValueError(f"{len(unknown)} personas are not in the team file, e.g. {unknown[:5]}")
    problems: List[str] = []
    for row in lin:
        base = by_id[row[lin_id_column]]
        for column in base:
            if column == "persona_id" or column not in row:
                continue
            if not same_value(base[column], row[column]):
                problems.append(f"{row[lin_id_column]} {column}: team {base[column]!r}, driver file {row[column]!r}")
        for column in DRIVER_COLUMNS:
            if not row[column].strip():
                problems.append(f"{row[lin_id_column]} {column} is blank")
        donor = row[DONOR_COLUMN].strip()
        half = split.get(donor)
        if half != "cal":
            problems.append(f"{row[lin_id_column]} donor {donor!r} is {'not in the split file' if half is None else 'in the ' + half + ' half'}")
    if problems:
        raise ValueError(f"{len(problems)} problems, e.g. " + "; ".join(problems[:5]))
    lin_by_id = {row[lin_id_column]: row for row in lin}
    merged = []
    for base in team:
        extra = lin_by_id.get(base["persona_id"])
        if extra is not None:
            merged.append({**base, **{c: extra[c].strip() for c in [*DRIVER_COLUMNS, DONOR_COLUMN]}})
    return merged


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lin", type=Path, required=True, help="Dr. Lin's personas_S*_drv.csv")
    parser.add_argument("--lin-id-column", default="persona_id", help="her column holding the team file's persona_id (team_s1_id for S1)")
    parser.add_argument("--team", type=Path, required=True, help="the team's persona file those ids refer to")
    parser.add_argument("--split", type=Path, required=True, help="her aytm_respondent_split_ids.csv")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    out = make_real_split.assert_outside_repo(realdata.assert_not_real_data_path(args.out, "--out"), "--out")
    team_rows = read_csv(args.team)
    split = {row["respondent_id"].strip(): row["rsplit"].strip() for row in read_csv(args.split)}
    try:
        merged = merge(read_csv(args.lin), team_rows, split, args.lin_id_column)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    header = [*team_rows[0].keys(), *DRIVER_COLUMNS, DONOR_COLUMN]
    with open(out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(merged)
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "script": "research/neo_persona_set/phase3/import_driver_personas.py",
        "persona_kind": "hybrid",
        "n_personas": len(merged),
        "lin_id_column": args.lin_id_column,
        "inputs": {name: {"path": str(Path(path).resolve()), "sha256": filter_qualified.sha256_of_file(Path(path))}
                   for name, path in (("driver_file", args.lin), ("team_file", args.team), ("split_file", args.split))},
        "output_sha256": filter_qualified.sha256_of_file(out),
        "checks": "persona columns equal the team file; drivers filled; every donor in the cal half",
    }
    Path(f"{out}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(merged)} hybrid personas to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
