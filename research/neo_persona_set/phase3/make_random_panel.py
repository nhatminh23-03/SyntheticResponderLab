"""Write a random-answer control panel, to put beside every real arm.

Mean total-variation distance falls whenever the synthetic side is more spread out, whether or not
the spread carries information. On the S1 panel a purely random panel scores mean_tv 0.212 against
0.244 for the best engineered panel and 0.399 for the DeepSeek baseline, with 5 of 36 questions
inside the 0.10 threshold against 2. So mean_tv cannot carry a claim that respondents became more
realistic, and no distance result should be reported without this arm next to it.

The metrics that do separate signal from noise are the ones where this control collapses:
mean_spearman 0.17 and share_top_match 0.25, against 0.53 and 0.53 for the engineered panel.

Two construction details decide whether the control is comparable at all:

  * likert answers are written as digits, not option labels. The runner writes digits, and
    compare_real.py reads a label as no data, which silently drops 17 of the 36 questions.
  * the screener and the demographic items are held at a real arm's values. Random answers to the
    outdoor-space screener trip compare_real's own filter, which dropped 39 of 100 personas and cut
    the comparable questions to 19 — a mean over a different, easier subset of questions.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/make_random_panel.py \
        --template out/survey_runs/<any completed run> --repeats 2
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Held at the template's values. The screener gates who is comparable at all; the demographics are
# persona attributes a generator would never be asked to invent, so randomising them would make the
# control weaker than random rather than stronger.
HOLD = {"S3", "Q21", "Q22", "Q23", "Q25", "Q26", "Q30"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--template", type=Path, required=True,
                        help="a completed run folder; its personas, questions and held answers are reused")
    parser.add_argument("--out-dir", type=Path, default=Path("out/survey_runs"))
    parser.add_argument("--run-tag", default="s1-RANDOM")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--seed", type=int, default=4242)
    args = parser.parse_args()

    with (args.template / "questions.csv").open(newline="", encoding="utf-8-sig") as handle:
        qrows = list(csv.DictReader(handle))
    kind = {r["question_id"]: r.get("question_type", "") for r in qrows}
    options = {r["question_id"]: (r["options"].split("|") if r.get("options") else []) for r in qrows}
    with (args.template / "answers_wide.csv").open(newline="", encoding="utf-8-sig") as handle:
        base = list(csv.DictReader(handle))
    header = list(base[0].keys())

    for repeat in range(1, args.repeats + 1):
        rng = random.Random(args.seed + repeat)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{stamp}_random-uniform_r{repeat}_{args.run_tag}"
        run_dir = args.out_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(args.template / "questions.csv", run_dir / "questions.csv")

        with (run_dir / "answers_wide.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            for row in base:
                out: Dict[str, str] = dict(row)
                out["run_id"], out["model"] = run_id, "random-uniform"
                for question in header:
                    if question not in kind or question in HOLD:
                        continue
                    if kind[question] == "likert":
                        out[question] = str(rng.randint(1, 5))
                    elif kind[question] == "multi_choice" and len(options[question]) >= 2:
                        out[question] = "|".join(rng.sample(options[question], 2))
                    elif options[question]:
                        out[question] = rng.choice(options[question])
                writer.writerow({k: out.get(k, "") for k in header})

        manifest = {
            "run_id": run_id,
            "status": "completed",
            "model": {"requested": "random-uniform", "arms": [], "note": "no model was called"},
            "panel": {"n_personas": len(base), "seed": args.seed + repeat, "repeat": repeat,
                      "template": str(args.template)},
            "held_from_template": sorted(HOLD),
            "notes": ("Control. Likert answers uniform on 1-5, choices uniform on the question's own "
                      "option list, multi-select two distinct options. The screener and the "
                      "demographic items are copied from the template so the comparable-question "
                      "count and the outdoor-space filter match the real arms."),
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"  {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
