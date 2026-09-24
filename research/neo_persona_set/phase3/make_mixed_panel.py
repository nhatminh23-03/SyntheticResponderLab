"""Materialise a mixed panel as a run folder, so it can be scored like any single-model run.

R018 found that assigning each persona to one of several arms beats every arm on its own. That
panel is a reanalysis rather than a run, so there is no folder for compare_real.py to read. This
writes one: personas are dealt round-robin over the named arms in a shuffled order, each persona's
answers are taken from the arm it was dealt, and the result is written in the layout
phase2/run_survey.py produces.

Dealing is by persona rather than by response, so a respondent's 39 answers all come from the same
model and the within-respondent structure of each arm is preserved. `--repeat` picks which repeat of
each arm to draw from, so repeat 1 and repeat 2 stay separable downstream.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/make_mixed_panel.py \
        --arm out/survey_runs/<gpt run> --arm out/survey_runs/<styled gemini run> \
        --arm out/survey_runs/<styled mistral run> --run-tag s1-R018-mixed
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


def read_wide(run_dir: Path) -> List[Dict[str, str]]:
    with (run_dir / "answers_wide.csv").open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", type=Path, action="append", required=True,
                        help="a run folder to draw from; repeat the flag once per arm")
    parser.add_argument("--out-dir", type=Path, default=Path("out/survey_runs"))
    parser.add_argument("--run-tag", default="s1-R018-mixed")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260924)
    args = parser.parse_args()

    arms = {d.name: read_wide(d) for d in args.arm}
    by_arm_persona = {name: {r["persona_id"]: r for r in rows} for name, rows in arms.items()}
    names = sorted(arms)
    # Only personas every arm answered, so the panel is the same 100 people as each arm.
    shared = sorted(set.intersection(*(set(v) for v in by_arm_persona.values())))

    order = shared[:]
    random.Random(args.seed).shuffle(order)
    assignment = {pid: names[i % len(names)] for i, pid in enumerate(order)}

    started = datetime.now(timezone.utc)
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}_mixed-panel_r{args.repeat}_{args.run_tag}"
    run_dir = args.out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    template = args.arm[0]
    shutil.copy(template / "questions.csv", run_dir / "questions.csv")

    header = list(read_wide(template)[0].keys())
    with (run_dir / "answers_wide.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for pid in shared:
            row = dict(by_arm_persona[assignment[pid]][pid])
            row["run_id"] = run_id
            # Without this the panel inherits whichever arm's model name happened to be in the
            # first row, and compare_real labels the whole run after one of its three models.
            if "model" in row:
                row["model"] = "mixed panel"
            writer.writerow({k: row.get(k, "") for k in header})

    # answers_long carries the fallback flags compare_real reads under --exclude-fallback, so the
    # rows for the personas actually used are carried across rather than regenerated.
    long_header: List[str] = []
    long_rows: List[Dict[str, str]] = []
    for name, d in zip(names, sorted(args.arm, key=lambda p: p.name)):
        path = d / "answers_long.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            long_header = long_header or list(reader.fieldnames or [])
            for row in reader:
                if assignment.get(row["persona_id"]) == d.name:
                    row["run_id"] = run_id
                    long_rows.append(row)
    if long_header:
        with (run_dir / "answers_long.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=long_header)
            writer.writeheader()
            writer.writerows(long_rows)

    counts: Dict[str, int] = {}
    for pid in shared:
        counts[assignment[pid]] = counts.get(assignment[pid], 0) + 1
    manifest = {
        "run_id": run_id,
        "status": "completed",
        "started_at": started.isoformat(),
        "script": {"path": "research/neo_persona_set/phase3/make_mixed_panel.py"},
        "model": {"requested": "mixed panel", "arms": names, "personas_per_arm": counts},
        "panel": {"n_personas": len(shared), "seed": args.seed, "repeat": args.repeat},
        "notes": ("Derived panel, no API calls. Each persona was dealt to one arm and its whole "
                  "39-answer record taken from that arm, so within-respondent structure is intact."),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{run_dir}\n  {len(shared)} personas: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
