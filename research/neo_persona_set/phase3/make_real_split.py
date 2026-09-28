"""Split the real respondents into a fitting half and a scoring half, by Response ID.

Anything fitted to real answers (driver donors, model adjustments) may use only the fit half, and
results are scored only against the score half, so nothing is graded on the people it was tuned
on. The halves are written as id files, which come from the real file, so they must stay outside
the repository and outside the real-data folder; this script refuses either place.

PROVISIONAL: Dr. Lin split the AYTM respondents 300/300 with seed 42, but her exact method is not
known, so this split will not match hers. Use her id lists once she shares them;
compare_real.py --real-ids reads either.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/make_real_split.py \\
        --real "<AYTM raw-data csv>" --out ../SyntheticResponderLab-Assets/real_splits/provisional-seed42
"""

from __future__ import annotations

import argparse
import json
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


def split_ids(ids: List[str], seed: int, fit_share: float = 0.5) -> Tuple[List[str], List[str]]:
    """(fit, score), each kept in file order."""
    order = list(ids)
    random.Random(seed).shuffle(order)
    fit_set = set(order[: round(len(order) * fit_share)])
    return [item for item in ids if item in fit_set], [item for item in ids if item not in fit_set]


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
    parser.add_argument("--label", default="provisional", help="recorded in split.json and the id files")
    args = parser.parse_args(argv)

    real_path = Path(args.real).expanduser().resolve()
    out = realdata.assert_outside_real_folder(args.out, real_path, "--out")
    out = assert_outside_repo(out, "--out")
    real = realdata.load_real_survey(real_path)
    ids = [value.strip() for value in real.values(realdata.RESPONSE_ID_KEY)]
    fit, score = split_ids(ids, args.seed, args.fit_share)

    out.mkdir(parents=True, exist_ok=True)
    note = "PROVISIONAL: not Dr. Lin's split; replace with her id lists when shared." if args.label == "provisional" else f"label: {args.label}"
    for name, half, use in (("fit_ids.txt", fit, "fit half: may be used for fitting (driver donors, model adjustments)"),
                            ("score_ids.txt", score, "score half: used only for scoring")):
        write_ids(out / name, half, f"{use}\n{len(half)} of {len(ids)} AYTM respondents; seed {args.seed}\n{note}")
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "script": "research/neo_persona_set/phase3/make_real_split.py",
        "label": args.label,
        "method": METHOD,
        "seed": args.seed,
        "fit_share": args.fit_share,
        "real": {"path": str(real_path), "sha256": filter_qualified.sha256_of_file(real_path), "n_rows": real.n},
        "n_fit": len(fit),
        "n_score": len(score),
    }
    (out / "split.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(fit)} fit / {len(score)} score ids to {out} ({args.label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
