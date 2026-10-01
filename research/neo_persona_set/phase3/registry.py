"""One row per hypothesis tested: what changed, which runs, how close to the real 600, and the decision.

    registry.py add --hypothesis "..." --condition "..." --flags "..." [--runs id;id] [--panel f] [--survey f] [--notes ...]
    registry.py fill --registry-id R003 --summary <real_comparison>/comparison_summary.csv
    registry.py show
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "registry.csv"
COLUMNS = ["registry_id", "date", "hypothesis", "condition", "runner_flags", "panel_file", "survey_file", "runs",
           "metric_tv_mean", "metric_close_count", "metric_top_match_share", "result", "decision", "notes"]
ENCODING = "utf-8-sig"


def read_entries(path: Path) -> List[Dict[str, str]]:
    if not Path(path).is_file():
        return []
    with open(path, newline="", encoding=ENCODING) as handle:
        return [{c: row.get(c, "") for c in COLUMNS} for row in csv.DictReader(handle)]


def write_entries(path: Path, rows: List[Dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding=ENCODING) as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def next_id(rows: List[Dict[str, str]]) -> str:
    """One past the highest number in use; ids such as R019b and rows added out of order are allowed."""
    numbers = [int(m.group(1)) for m in (re.match(r"^R(\d+)", row["registry_id"]) for row in rows) if m]
    return f"R{max(numbers, default=0) + 1:03d}"


def add_entry(path: Path, **fields: str) -> str:
    rows = read_entries(path)
    entry = {c: "" for c in COLUMNS}
    entry.update({k: v for k, v in fields.items() if k in COLUMNS and v is not None})
    if any(row["registry_id"] == entry["registry_id"] for row in rows):
        raise ValueError(f"registry id {entry['registry_id']} is already in {path}")
    entry["registry_id"] = entry["registry_id"] or next_id(rows)
    entry["date"] = entry["date"] or datetime.now(timezone.utc).date().isoformat()
    rows.append(entry)
    write_entries(path, rows)
    return entry["registry_id"]


def fill_metrics(path: Path, registry_id: str, summary_csv: Path) -> Dict[str, str]:
    rows = read_entries(path)
    entry = next((r for r in rows if r["registry_id"] == registry_id), None)
    if entry is None:
        raise KeyError(registry_id)
    with open(summary_csv, newline="", encoding=ENCODING) as handle:
        summary = list(csv.DictReader(handle))
    wanted = {r.strip() for r in entry["runs"].split(";") if r.strip()}
    picked = [r for r in summary if not wanted or r["run_id"] in wanted]
    if not picked:
        raise ValueError(f"no summary rows match runs {sorted(wanted)}")
    tv = sum(float(r["mean_tv"]) for r in picked) / len(picked)
    close = sum(int(float(r["questions_close"])) for r in picked)
    top = sum(float(r["share_top_match"]) for r in picked) / len(picked)
    metrics = {"metric_tv_mean": f"{tv:.4f}", "metric_close_count": str(close), "metric_top_match_share": f"{top:.4f}"}
    entry.update(metrics)
    write_entries(path, rows)
    return metrics


def render_table(path: Path) -> str:
    rows = read_entries(path)
    shown = ["registry_id", "date", "hypothesis", "condition", "runs", "metric_tv_mean", "metric_close_count", "metric_top_match_share", "decision"]
    lines = ["| " + " | ".join(shown) + " |", "| " + " | ".join("---" for _ in shown) + " |"]
    lines += ["| " + " | ".join(row[c].replace("|", "/") for c in shown) + " |" for row in rows]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--registry-id", default="", help="an explicit id such as R020b (default: the next number)")
    add.add_argument("--date", default="", help="YYYY-MM-DD (default: today, UTC)")
    add.add_argument("--hypothesis", required=True)
    add.add_argument("--condition", required=True)
    add.add_argument("--flags", dest="runner_flags", default="")
    add.add_argument("--runs", default="")
    add.add_argument("--panel", dest="panel_file", default="")
    add.add_argument("--survey", dest="survey_file", default="")
    add.add_argument("--notes", default="")
    fill = sub.add_parser("fill")
    fill.add_argument("--registry-id", required=True)
    fill.add_argument("--summary", type=Path, required=True)
    sub.add_parser("show")
    argv = list(sys.argv[1:] if argv is None else argv)
    for index, token in enumerate(argv[:-1]):  # runner flags start with "--", which argparse would read as options
        if token == "--flags":
            argv[index : index + 2] = [f"--flags={argv[index + 1]}"]
            break
    args = parser.parse_args(argv)
    if args.command == "add":
        print(add_entry(args.registry, registry_id=args.registry_id, date=args.date, hypothesis=args.hypothesis, condition=args.condition, runner_flags=args.runner_flags,
                        runs=args.runs, panel_file=args.panel_file, survey_file=args.survey_file, notes=args.notes))
    elif args.command == "fill":
        print(fill_metrics(args.registry, args.registry_id, args.summary))
    else:
        print(render_table(args.registry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
