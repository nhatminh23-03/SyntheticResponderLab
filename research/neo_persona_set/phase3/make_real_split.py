"""Split the real respondents into a fitting half and a scoring half, by Response ID.

Anything fitted to real answers (driver donors, model adjustments) may use only the fit half, and
results are scored only against the score half, so nothing is graded on the people it was tuned
on. The halves are written as id files, which come from the real file, so they must stay outside
the repository and outside the real-data folder; this script refuses either place.

Two modes:
- --from-lin converts Dr. Lin's split (aytm_respondent_split_ids.csv, shared 2026-09-30) into id
  files. His ids are row indexes, aytm_N = respondent row N of the raw file in file order; the
  conversion looks up each row's Response ID. This is the split all scoring uses.
- without it, a new seeded split is drawn. That was the PROVISIONAL stand-in before his file came.
compare_real.py --real-ids reads the id files either mode writes.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/make_real_split.py \\
        --real "<AYTM raw-data csv>" --from-lin <aytm_respondent_split_ids.csv> \\
        --out ../SyntheticResponderLab-Assets/3_scoring_standard/real_splits/lin-seed42
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import filter_qualified  # noqa: E402
import realdata  # noqa: E402

METHOD = "Response IDs in file order, random.Random(seed).shuffle, first round(n * fit_share) are the fit half"
LIN_METHOD = ("Dr. Lin's aytm_respondent_split_ids.csv: aytm_N is respondent row N (from 0) of the raw file in "
              "file order, mapped to that row's Response ID; rsplit cal = fit half, val = score half")
LIN_HALVES = {"cal": "fit", "val": "score"}
_LIN_ID = re.compile(r"^aytm_(\d+)$")


def split_ids(ids: List[str], seed: int, fit_share: float = 0.5) -> Tuple[List[str], List[str]]:
    """(fit, score), each kept in file order."""
    order = list(ids)
    random.Random(seed).shuffle(order)
    fit_set = set(order[: round(len(order) * fit_share)])
    return [item for item in ids if item in fit_set], [item for item in ids if item not in fit_set]


def split_from_lin(path: Path, real: "realdata.RealSurvey") -> Tuple[List[str], List[str], int]:
    """(fit, score, seed) from Dr. Lin's split file; each half in file order. Raises ValueError on a mismatch."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = [{key.strip(): (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]
    ids = [row.get("respondent_id", "") for row in rows]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate respondent ids {duplicates[:5]}")
    if len(rows) != real.n:
        raise ValueError(f"{path}: {len(rows)} rows, but the real file has {real.n} respondents")
    indexes = [int(m.group(1)) if m else -1 for m in (_LIN_ID.match(item) for item in ids)]
    if sorted(indexes) != list(range(real.n)):
        raise ValueError(f"{path}: respondent ids must be exactly aytm_0 .. aytm_{real.n - 1}")
    unknown = sorted({row.get("rsplit", "") for row in rows} - set(LIN_HALVES))
    if unknown:
        raise ValueError(f"{path}: unknown half {unknown}; expected {sorted(LIN_HALVES)}")
    seeds = {row.get("seed", "") for row in rows}
    if len(seeds) != 1:
        raise ValueError(f"{path}: expected one seed, found {sorted(seeds)}")
    response_ids = [value.strip() for value in real.values(realdata.RESPONSE_ID_KEY)]
    half_of = {response_ids[index]: LIN_HALVES[row["rsplit"]] for index, row in zip(indexes, rows)}
    fit = [item for item in response_ids if half_of[item] == "fit"]
    score = [item for item in response_ids if half_of[item] == "score"]
    return fit, score, int(seeds.pop())


def assert_outside_repo(path: Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        print(f"REFUSED: {label} path {resolved} is inside the repository; ids from the real file are not committed.", file=sys.stderr)
        raise realdata.RealDataPathError(f"{label} path is inside the repository: {resolved}")
    return resolved


def write_ids(path: Path, ids: List[str], header: str) -> None:
    path.write_text("".join(f"# {line}\n" for line in header.splitlines()) + "\n".join(ids) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--real", type=Path, required=True, help="the AYTM raw-data CSV")
    parser.add_argument("--out", type=Path, required=True, help="folder for fit_ids.txt, score_ids.txt, split.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fit-share", type=float, default=0.5)
    parser.add_argument("--label", default=None, help="recorded in split.json and the id files (default: provisional, or lin-seed<seed> with --from-lin)")
    parser.add_argument("--from-lin", type=Path, default=None, help="Dr. Lin's aytm_respondent_split_ids.csv; converted, not redrawn")
    args = parser.parse_args(argv)

    real_path = Path(args.real).expanduser().resolve()
    out = realdata.assert_outside_real_folder(args.out, real_path, "--out")
    out = assert_outside_repo(out, "--out")
    real = realdata.load_real_survey(real_path)
    ids = [value.strip() for value in real.values(realdata.RESPONSE_ID_KEY)]
    source = None
    if args.from_lin is not None:
        lin_path = Path(args.from_lin).expanduser().resolve()
        try:
            fit, score, seed = split_from_lin(lin_path, real)
        except ValueError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        label, method = args.label or f"lin-seed{seed}", LIN_METHOD
        note = "Dr. Lin's split, converted from his row indexes (aytm_N = row N; confirmation pending)."
        source = {"path": str(lin_path), "sha256": filter_qualified.sha256_of_file(lin_path)}
    else:
        seed = args.seed
        fit, score = split_ids(ids, seed, args.fit_share)
        label, method = args.label or "provisional", METHOD
        note = "PROVISIONAL: not Dr. Lin's split; replace with his id lists when shared." if label == "provisional" else f"label: {label}"

    out.mkdir(parents=True, exist_ok=True)
    for name, half, use in (("fit_ids.txt", fit, "fit half: may be used for fitting (driver donors, model adjustments)"),
                            ("score_ids.txt", score, "score half: used only for scoring")):
        write_ids(out / name, half, f"{use}\n{len(half)} of {len(ids)} AYTM respondents; seed {seed}\n{note}")
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "script": "research/neo_persona_set/phase3/make_real_split.py",
        "label": label,
        "method": method,
        "seed": seed,
        "fit_share": round(len(fit) / len(ids), 4) if source else args.fit_share,
        "real": {"path": str(real_path), "sha256": filter_qualified.sha256_of_file(real_path), "n_rows": real.n},
        "n_fit": len(fit),
        "n_score": len(score),
    }
    if source:
        record["source"] = source
    (out / "split.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(fit)} fit / {len(score)} score ids to {out} ({label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
