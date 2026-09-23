"""Score a run against the real 600 using marginals already extracted by compare_real.py.

compare_real.py needs the AYTM raw-data CSV, which is deliberately kept off this machine. But a
comparison folder it produced earlier carries, for every question and option, the real count and
share alongside the synthetic ones. Those real columns are a property of the real 600, not of the
run they were computed against, so they can be lifted out once and reused to score any later run.

That gives the same marginal metrics compare_real.py reports — mean total-variation distance, the
share of questions within a threshold, and the share whose most-common answer matches — without
the raw file. It does NOT give the metrics that need the real respondent-level joins, so
mean_spearman and the chi-square counts are not reproduced here.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/score_vs_real_marginals.py \\
        --real-from <a compare_real output folder> \\
        --arm gemini=<run_r1>,<run_r2> [--arm ...] [--out scores.csv]
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLOSE_TV = 0.10

# Three questions need the label normalisation that lives inside compare_real.py, which this
# script does not reimplement, so they are left out rather than scored wrongly:
#   Q14  our concept labels carry a tagline that compare_real strips before matching on the
#        concept number, so the raw labels never line up with the real ones;
#   Q20  multi-select, compared option by option on the share of respondents selecting each,
#        not as one distribution over pipe-joined combinations;
#   Q22  our income bands are collapsed onto the real five, and our "Prefer not to say" has no
#        real counterpart.
# Every other question this script scores reproduces compare_real's own per-question TV to within
# 0.005 on Minh's baseline runs, which is what makes the remaining numbers comparable to his.
NEEDS_COMPARE_REAL = {"Q14", "Q20", "Q22"}


def load_real_marginals(folder: Path) -> Dict[str, Dict[str, float]]:
    """{our_id: {option: real_share}} from one compare_real output folder.

    The file repeats every (question, option) row once per run compared in that folder, and the
    real columns are identical across those repeats because they describe the real 600 rather than
    the run. So every row is read and duplicates simply overwrite with the same value; the rows are
    interleaved by run rather than grouped, so stopping at the first run id would read one question.
    """
    path = folder / "comparison_options.csv"
    real: Dict[str, Dict[str, float]] = defaultdict(dict)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            real[row["our_id"]][row["category"]] = float(row["real_share"])
    return dict(real)


def read_wide(run_dir: Path) -> List[Dict[str, str]]:
    with (run_dir / "answers_wide.csv").open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def tv(a: Dict[str, float], b: Dict[str, float]) -> float:
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))


def js(a: Dict[str, float], b: Dict[str, float]) -> float:
    total = 0.0
    for key in set(a) | set(b):
        p, q = a.get(key, 0.0), b.get(key, 0.0)
        m = 0.5 * (p + q)
        if p:
            total += 0.5 * p * math.log2(p / m)
        if q:
            total += 0.5 * q * math.log2(q / m)
    return total


def score(arm: str, run_dirs: List[Path], real: Dict[str, Dict[str, float]],
          require_outdoor_space: bool) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    rows: List[Dict[str, str]] = []
    for d in run_dirs:
        rows += read_wide(d)
    dropped = 0
    if require_outdoor_space:
        # compare_real drops our personas who answered No to the outdoor-space screener, because
        # real respondents who answered No were terminated and never reached the rest of the survey.
        kept = [r for r in rows if str(r.get("S3", "")).strip().lower() != "no"]
        dropped, rows = len(rows) - len(kept), kept

    per_question: List[Dict[str, object]] = []
    for our_id, real_shares in sorted(real.items()):
        if our_id in NEEDS_COMPARE_REAL:
            continue
        answers = [str(r.get(our_id, "")).strip() for r in rows]
        answers = [a for a in answers if a]
        if not answers:
            continue
        counts = Counter(answers)
        n = sum(counts.values())
        synth = {k: v / n for k, v in counts.items()}
        if not set(synth) & set(real_shares):
            continue  # option labels do not line up; compare_real reports these as unmapped
        per_question.append({
            "arm": arm,
            "question": our_id,
            "tv": tv(real_shares, synth),
            "js": js(real_shares, synth),
            "top_match": int(max(real_shares, key=real_shares.get) == counts.most_common(1)[0][0]),
        })

    tvs = [float(q["tv"]) for q in per_question]
    summary = {
        "arm": arm,
        "runs": len(run_dirs),
        "n_rows": len(rows),
        "n_dropped_outdoor": dropped,
        "questions_compared": len(per_question),
        "mean_tv": round(sum(tvs) / len(tvs), 4) if tvs else float("nan"),
        "median_tv": round(sorted(tvs)[len(tvs) // 2], 4) if tvs else float("nan"),
        "mean_js": round(sum(float(q["js"]) for q in per_question) / len(per_question), 4) if per_question else float("nan"),
        "share_close": round(sum(1 for t in tvs if t <= CLOSE_TV) / len(tvs), 4) if tvs else float("nan"),
        "share_top_match": round(sum(int(q["top_match"]) for q in per_question) / len(per_question), 4) if per_question else float("nan"),
    }
    return summary, per_question


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--real-from", type=Path, required=True, help="a folder written by compare_real.py")
    parser.add_argument("--arm", action="append", required=True, metavar="NAME=RUN_DIR[,RUN_DIR...]")
    parser.add_argument("--keep-all", dest="require_outdoor_space", action="store_false", default=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--per-question", type=Path, default=None)
    args = parser.parse_args(argv)

    real = load_real_marginals(args.real_from)
    print(f"real marginals for {len(real)} questions, from {args.real_from.name}\n")

    summaries, details = [], []
    for spec in args.arm:
        name, _, paths = spec.partition("=")
        dirs = [Path(p.strip()) for p in paths.split(",") if p.strip()]
        summary, per_question = score(name.strip(), dirs, real, args.require_outdoor_space)
        summaries.append(summary)
        details += per_question

    header = ["arm", "questions_compared", "mean_tv", "median_tv", "mean_js", "share_close", "share_top_match", "n_rows", "n_dropped_outdoor"]
    widths = {"arm": 34}
    print(" ".join(f"{h:<{widths.get(h, 18)}}" for h in header))
    print("-" * 150)
    for s in summaries:
        print(" ".join(f"{str(s[h]):<{widths.get(h, 18)}}" for h in header))

    if args.out:
        with args.out.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summaries[0].keys()))
            writer.writeheader()
            writer.writerows(summaries)
    if args.per_question:
        with args.per_question.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["arm", "question", "tv", "js", "top_match"])
            writer.writeheader()
            writer.writerows(details)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
