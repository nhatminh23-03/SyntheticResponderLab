"""Materialise a mixed panel as a run folder, so it can be scored like any single-model run.

R018 found that assigning each persona to one of several arms beats every arm on its own. That
panel is a reanalysis rather than a run, so there is no folder for compare_real.py to read. This
writes one: personas are dealt round-robin over the named arms in a shuffled order, each persona's
answers are taken from the arm it was dealt, and the result is written in the layout
phase2/run_survey.py produces.

Dealing is by persona rather than by response, so a respondent's 39 answers all come from the same
model and the within-respondent structure of each arm is preserved. `--repeat` picks which repeat of
each arm to draw from, so repeat 1 and repeat 2 stay separable downstream.

Arms must agree on the persona file, the seed, the answer mode, the persona kind (hybrid or not)
and the response-style mix, so that the only thing the mix varies is the model. A styled arm and an
unstyled arm are refused together unless --allow-mismatch trait_mix says so (R018 did that on
purpose); the persona file, answer mode and persona kind can never differ. Under --answer-mode
distribution the dealt personas' rows of probabilities.csv are carried across as well.

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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Settings every arm must share; only these two may be allowed to differ.
CHECKED = ("persona_sha256", "seed", "answer_mode", "persona_kind", "trait_mix")
MAY_DIFFER = ("trait_mix", "seed")


def read_wide(run_dir: Path) -> List[Dict[str, str]]:
    with (run_dir / "answers_wide.csv").open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def arm_settings(run_dir: Path) -> Dict[str, Any]:
    """The CHECKED settings from an arm's manifest; runs from before a setting existed get its default."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        "persona_sha256": (manifest.get("personas") or {}).get("sha256"),
        "seed": manifest.get("seed"),
        "answer_mode": manifest.get("answer_mode") or "single",
        "persona_kind": manifest.get("persona_kind") or "synthetic",
        "trait_mix": manifest.get("trait_mix") or None,
    }


def mismatches(settings: Dict[str, Dict[str, Any]], allowed: List[str]) -> List[str]:
    problems = []
    for field in CHECKED:
        values = {name: s[field] for name, s in settings.items()}
        if len(set(map(str, values.values()))) > 1 and field not in allowed:
            problems.append(f"{field} differs between arms: " + ", ".join(f"{name}={value}" for name, value in sorted(values.items())))
    return problems


def carry_rows(arms: List[Path], assignment: Dict[str, str], filename: str, run_id: str, out: Path) -> None:
    """Copy each dealt persona's rows of `filename` from the arm it was dealt to."""
    header: List[str] = []
    rows: List[Dict[str, str]] = []
    for arm in arms:
        path = arm / filename
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            header = header or list(reader.fieldnames or [])
            for row in reader:
                if assignment.get(row["persona_id"]) == arm.name:
                    row["run_id"] = run_id
                    rows.append(row)
    if header:
        with out.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)


def _common(settings: Dict[str, Dict[str, Any]], field: str) -> Optional[Any]:
    values = {str(s[field]) for s in settings.values()}
    return next(iter(settings.values()))[field] if len(values) == 1 else "differs by arm"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", type=Path, action="append", required=True,
                        help="a run folder to draw from; repeat the flag once per arm")
    parser.add_argument("--out-dir", type=Path, default=Path("out/survey_runs"))
    parser.add_argument("--run-tag", default="s1-R018-mixed")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260924)
    parser.add_argument("--keep-arm-order", action="store_true",
                        help="deal in the order the --arm flags are given rather than sorted by folder name; give the arms in "
                             "an earlier panel's model order to reproduce its persona -> model deal")
    parser.add_argument("--allow-mismatch", action="append", default=[], choices=MAY_DIFFER,
                        help="let this setting differ between arms (repeat for both); recorded in the manifest")
    args = parser.parse_args(argv)

    settings = {d.name: arm_settings(d) for d in args.arm}
    problems = mismatches(settings, args.allow_mismatch)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 2

    arms = {d.name: read_wide(d) for d in args.arm}
    by_arm_persona = {name: {r["persona_id"]: r for r in rows} for name, rows in arms.items()}
    # The deal walks a seeded shuffle of the persona ids and hands them out over `names` in turn, so
    # the same ids, seed and arm order give the same persona -> arm deal. Folder names start with a
    # timestamp, so sorting them puts later reruns of the same models in a different order.
    names = [d.name for d in args.arm] if args.keep_arm_order else sorted(arms)
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
    # rows for the personas actually used are carried across rather than regenerated; likewise the
    # stated odds under --answer-mode distribution.
    for filename in ("answers_long.csv", "probabilities.csv"):
        carry_rows(sorted(args.arm, key=lambda p: p.name), assignment, filename, run_id, run_dir / filename)

    counts: Dict[str, int] = {}
    for pid in shared:
        counts[assignment[pid]] = counts.get(assignment[pid], 0) + 1
    manifest = {
        "run_id": run_id,
        "status": "completed",
        "started_at": started.isoformat(),
        "script": {"path": "research/neo_persona_set/phase3/make_mixed_panel.py"},
        "model": {"requested": "mixed panel", "arms": names, "personas_per_arm": counts},
        "panel": {"n_personas": len(shared), "seed": args.seed, "repeat": args.repeat,
                  "arm_order": "as given" if args.keep_arm_order else "sorted by folder name"},
        "answer_mode": _common(settings, "answer_mode"),
        "persona_kind": _common(settings, "persona_kind"),
        "trait_mix": _common(settings, "trait_mix"),
        "allowed_mismatch": sorted(args.allow_mismatch),
        "arm_settings": settings,
        "personas": {"sha256": _common(settings, "persona_sha256")},
        "notes": ("Derived panel, no API calls. Each persona was dealt to one arm and its whole "
                  "39-answer record taken from that arm, so within-respondent structure is intact."),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{run_dir}\n  {len(shared)} personas: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
