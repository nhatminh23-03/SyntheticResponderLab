"""Write START_HERE.md at the top of the shared Assets folder, and optionally refresh the codebook and crosswalk in 1_reference/.

The Assets folder is organized in numbered sections (2026-10-03): 0_logs, 1_reference, 2_real_data_aytm,
3_scoring_standard, 4_persona_sets, 5_experiments (one dated folder per experiment round) and 9_outbox.
FOLDER_MAP.csv at the top maps the old folder names to the new ones.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/write_start_here.py --assets ../SyntheticResponderLab-Assets \\
        [--keeper-run <a run folder whose questions.csv becomes 1_reference/questions.csv>] [--crosswalk <crosswalk.csv>]
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Top-level items, in reading order; each is listed only when present.
SECTIONS = OrderedDict([
    ("FOLDER_MAP.csv", "old folder → new folder for everything moved on 2026-10-03. Run manifests and emails written before then use the old paths."),
    ("0_logs", "`EXPERIMENT_LOG.md` (every run, its result and cost), `DISCUSSION_LOG.md` (week by week: what happened, decisions, next steps, the email archive), `emails_and_meetings/`, `reviews/`."),
    ("1_reference", "`questions.csv` (the 39-item codebook the synthetic respondents saw), `crosswalk.csv` (our question ids next to the real survey's columns), the app test log."),
    ("2_real_data_aytm", "the real AYTM respondents (raw CSV and summary PDF) and the Tony visit recording. Only compare_real.py reads it; the runner refuses any path containing aytm or survey-760085."),
    ("3_scoring_standard", "Dr. Lin's split as he sent it (`DrLin_split/`) and converted to Response IDs (`real_splits/lin-seed42/` is the standard; `provisional-seed42/` is superseded)."),
    ("4_persona_sets", "the synthetic respondents (see Persona sets below)."),
    ("5_experiments", "one folder per experiment round, oldest first (see Experiments below)."),
    ("9_outbox", "bundles prepared for OneDrive or email; delete once sent."),
])
PERSONA_SETS = OrderedDict([
    ("plain_600_2026-08-25", "the PLAIN draw: 600 California owner-occupied detached single-family households, income $100k+, householder 30-65, drawn at random from the Census (ACS PUMS 2024 5-year, seed 20260825). Describes Neo's likely buyers; cannot be validated against the real survey."),
    ("matched_600_v1_2026-09-09", "the first MATCHED draw: 600 households drawn nationally so age band x gender x income bracket x region reproduce the real 600 respondents (ACS PUMS 2024 1-year, seed 20260909, 199 cells, none short). Known issues: age_bucket and income_bucket carry the plain draw's labels, home_type is a constant, county is blank for national rows (the runner derives the buckets from the exact values; lint_personas.py reports the rest)."),
    ("matched_600_v2_S1-S6_2026-09-16", "Yaza's second matched 600, with the outdoor-space screen at the draw, split into six 100-persona subsets. `phase1_interview_matched600_s1.csv` is **S1**, the panel every experiment since Sept 17 uses; subset files number their personas P001-P100, and `panel_s*_ids.txt` / `subset_id_map.csv` map them to the full file's ids."),
    ("hybrid_drivers", "Dr. Lin's four driver answers (prior consideration, outdoor recreation, club membership, most likely use) copied from calibration-half respondents. `from_DrLin_2026-10-01/` as he sent them (S1 and his S2); `from_DrLin_2026-09-30_WRONG_S1_do_not_use/` (wrong 100 people); `run_ready/` merged onto the team's persona file by import_driver_personas.py. Run these only with --hybrid."),
])
EXPERIMENTS = OrderedDict([
    ("2026-09-10_first_full_600_runs", "first full runs (R001): DeepSeek and Qwen x 2 repeats on the plain 600 and the first matched 600, with the Sept 13 comparison of the matched runs."),
    ("2026-09-17_S1_prompt_and_sampling_tests", "S1 baseline and the prompt / sampling hypotheses R002-R011 (temperature, slicing the survey, sponsor text, interest note, reasons + judge). `real_comparison/` also holds the Sept 30 rescore on Dr. Lin's standard."),
    ("2026-09-24_Yaza_ablations_models_styles", "Yaza's Sept 23-24 runs: income ablations, other model families, Jev, logprobs, response styles, the R018 / R018b mixed panels and the random control, with his RESULTS and ALL_ARMS write-ups and the Sept 30 rescore."),
    ("2026-09-30_rescore_on_DrLin_standard", "R018u (the four models without styles, built from Yaza's Sept 23 runs, no new API calls) and the baselines scored on Dr. Lin's standard."),
    ("2026-10-01_R020_drivers_plus_drawing", "R020 / R020b: driver personas + answers drawn from stated probabilities on the four-model mix, unstyled and styled. R020 is the best setup so far."),
    ("2026-10-02_R021_drawing_only_vs_drivers_only", "R021 / R021b: drawing alone and drivers alone, to separate R020's two changes."),
])
RUN_FILES = OrderedDict([
    ("answers_long.csv", "one row per persona x question: run_id, model, repeat, seed, persona_id, respondent_id, question_id, question_type, answer, answer_json, is_fallback. Drop rows with is_fallback = true."),
    ("answers_wide.csv", "one row per persona, one column per question id, plus n_fallback and all_live. The file to load for analysis."),
    ("probabilities.csv", "runs with --answer-mode distribution only: the stated probability of every scale point, the drawn answer and a status."),
    ("questions.csv", "the codebook for this run (identical to 1_reference/questions.csv); has a preamble column when the survey reader carried stimulus text."),
    ("raw_responses.jsonl", "per persona: the model's raw text, serving host, model served, tokens, cost, attempts, finish reason."),
    ("generation_debug.json", "the engine's counters: executions, live vs fabricated answers, request errors."),
    ("prompt_sample.txt", "the exact prompt sent for the first persona."),
    ("summary.md", "Q1/Q2/Q6/Q14 answer shares, Q30 attention-check pass rate, Q21/Q22 agreement with the persona's exact age and income."),
    ("manifest.json", "everything needed to reproduce: sha256 of inputs and outputs, settings, seed, counts, tokens, cost, guardrail verdict, git commit. Paths in manifests written before 2026-10-03 use the old folder names (FOLDER_MAP.csv)."),
])


def read_index(index_path: Path) -> List[Dict[str, str]]:
    with open(index_path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def classify_runs(survey_runs: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Runs listed in survey_runs/index.csv, split into keepers and smoke / failed runs."""
    result: Dict[str, List[Dict[str, Any]]] = {"keepers": [], "other": []}
    index_path = survey_runs / "index.csv"
    if not index_path.is_file():
        return result
    for row in read_index(index_path):
        run_id = row.get("run_id", "")
        folder = run_id if (survey_runs / run_id).is_dir() else f"{run_id}_failed"
        entry = {**row, "folder": folder}
        reasons = []
        if (row.get("limit") or "").strip():
            reasons.append(f"smoke test ({row['limit']} personas)")
        if row.get("status") != "completed":
            reasons.append("failed guardrail")
        if reasons:
            entry["why"] = "; ".join(reasons)
            result["other"].append(entry)
        else:
            result["keepers"].append(entry)
    return result


def _table(header: List[str], rows: List[List[str]]) -> List[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def survey_run_dirs(experiment: Path) -> List[Path]:
    """Every survey_runs/ folder at most two levels inside an experiment folder."""
    return sorted(p for p in list(experiment.glob("survey_runs")) + list(experiment.glob("*/survey_runs")) if p.is_dir())


def classify_by_name(name: str) -> str:
    """For run folders not in an index.csv: model, mixed, smoke or failed, from the folder name."""
    if name.endswith("_failed"):
        return "failed"
    if re.search(r"_n\d+_", name) or "smoke" in name:
        return "smoke"
    if "mixed-panel" in name:
        return "mixed"
    return "model"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def describe_experiment(experiment: Path) -> List[str]:
    lines = [f"### `{experiment.name}/`", "", EXPERIMENTS.get(experiment.name, "(no description yet: add one to EXPERIMENTS in write_start_here.py)"), ""]
    ignore: List[List[str]] = []
    for runs_dir in survey_run_dirs(experiment):
        rel = runs_dir.relative_to(experiment).as_posix()
        runs = classify_runs(runs_dir)
        indexed = {entry["folder"] for group in runs.values() for entry in group}
        unindexed = sorted(p.name for p in runs_dir.iterdir() if p.is_dir() and p.name not in indexed)
        kinds = {name: classify_by_name(name) for name in unindexed}
        count = {kind: sum(1 for k in kinds.values() if k == kind) for kind in ("model", "mixed", "smoke", "failed")}
        parts = []
        has_index = (runs_dir / "index.csv").is_file()
        if has_index:
            usd = sum(float(e.get("usd_reported") or 0) for e in runs["keepers"])
            parts.append(_plural(len(runs["keepers"]), "keeper") + " in index.csv" + (f" (${usd:.2f} reported)" if usd else ""))
        if count["model"]:
            parts.append(_plural(count["model"], "other model run" if has_index else "model run"))
        if count["mixed"]:
            parts.append(_plural(count["mixed"], "mixed panel"))
        bad = len(runs["other"]) + count["smoke"] + count["failed"]
        if bad:
            parts.append(f"{bad} smoke / failed")
        lines.append(f"- `{rel}/`: " + ("" if has_index else "no index.csv: ") + ", ".join(parts))
        ignore += [[f"`{rel}/{e['folder']}`", e["why"]] for e in runs["other"]]
        ignore += [[f"`{rel}/{name}`", "failed guardrail" if kind == "failed" else "smoke test"]
                   for name, kind in kinds.items() if kind in ("smoke", "failed")]
    if ignore:
        lines += ["", "Ignore for analysis (kept for audit):", ""] + _table(["folder", "why"], sorted(ignore))
    return lines + [""]


def render_start_here(*, assets: Path, keeper_run: Optional[Path], today: str) -> str:
    present = {child.name for child in assets.iterdir()}
    lines: List[str] = ["# START HERE — Neo Smart Living synthetic survey runs", "",
                        f"Updated {today} by research/neo_persona_set/phase3/write_start_here.py. Edit the script, not this file.", "",
                        "Read the folders in number order: the logs say what was done and why, the reference files define the survey, "
                        "the real data and scoring standard define what \"right\" means, the persona sets are the synthetic respondents, "
                        "and each experiment folder holds one round of runs and their scores.", "",
                        "## What is where", ""]
    top = [["`START_HERE.md`", "this file"]]
    top += [[f"`{name}`" if "." in name else f"`{name}/`", text] for name, text in SECTIONS.items() if name in present]
    lines += _table(["Item", "What it is"], top)
    if keeper_run is not None:
        lines += ["", f"`1_reference/questions.csv` was copied from run `{keeper_run.name}`."]
    lines += ["", "## How to score (from 2026-09-30)", "",
              "Dr. Lin's calibration / validation split is the standard. Score on his 13 validation items against his 300 held-out respondents:",
              "`compare_real.py --items lin13-validation --real-ids 3_scoring_standard/real_splits/lin-seed42/score_ids.txt`. Anything fitted to real answers (driver donors, adjustments) uses only `3_scoring_standard/real_splits/lin-seed42/fit_ids.txt` and the calibration items.",
              "Hybrid runs (persona files with driver answers copied from real respondents) carry `hybrid` in the folder name and `persona_kind: hybrid` in the manifest; they are never scored on the four driver questions.",
              "Read rank agreement (mean_spearman) and top-answer match first, with the random control alongside; mean TV alone can be beaten by random answers."]
    sets_dir = assets / "4_persona_sets"
    if sets_dir.is_dir():
        lines += ["", "## Persona sets (`4_persona_sets/`)", ""]
        rows = [[f"`{p.name}/`", PERSONA_SETS.get(p.name, "(no description yet: add one to PERSONA_SETS in write_start_here.py)")]
                for p in sorted(sets_dir.iterdir()) if p.is_dir()]
        lines += _table(["Folder", "What it is"], rows)
        lines += ["", "A persona file (`phase1_interview_*.csv`) has one row per persona: bucket fields, the exact Census record, a name and the story_* columns. Names are random and carry no information. `phase1_method_*.txt` says how the set was drawn."]
    exp_dir = assets / "5_experiments"
    if exp_dir.is_dir():
        lines += ["", "## Experiments (`5_experiments/`, oldest first)", ""]
        for experiment in sorted(p for p in exp_dir.iterdir() if p.is_dir()):
            lines += describe_experiment(experiment)
        lines += ["New runs go to `5_experiments/<YYYY-MM-DD>_<what>/survey_runs` (pass --out-dir); without it the runner writes to `5_experiments/new_runs/survey_runs`."]
    lines += ["", "## Inside an experiment folder", "",
              "- `survey_runs/`: one folder per model run (plus mixed panels), `index.csv` (one row per run incl. smoke and failed runs) and `cross_run_summary.md`.",
              "- `real_comparison/<stamp>/`: scoring against the real survey; start with `comparison_summary.csv` or `comparison_by_question.md`.",
              "", "## Run folder names", "", "`<timestamp>_<model>_r<repeat>[_n<limit>|_p<panel>][_<tag>][_failed]`", "",
              "- timestamp: start time in UTC, 20260910T014617Z = 2026-09-10 01:46:17 UTC.",
              "- model: the OpenRouter model without the vendor prefix (deepseek-v4-pro-0813, qwen3.7-plus), or `mixed-panel` for a panel built from several runs.",
              "- r1, r2: repeat number; each repeat uses seed 20260909 * 10 + repeat with temperature 0.2.",
              "- n5: only the first 5 personas (a smoke test). p100: a fixed panel of 100.",
              "- tag: free text given at run time (e.g. s1-baseline, s1-R020-hybrid-draw-unstyled). `hybrid` in the tag means driver personas.",
              "- _failed: the run tripped a guardrail. Kept for audit, never used.",
              "", "## The files in a run folder", ""]
    lines += _table(["File", "What it holds"], [[f"`{name}`", text] for name, text in RUN_FILES.items()])
    lines += ["", "## Question ids", "",
              "39 items in survey order: S3 (screener), Q0A, Q0B, Q1, Q2, Q3, Q5_1-Q5_7 (the seven rows of the barrier matrix), Q6, Q7, Q9A/Q9B ... Q13A/Q13B (appeal and purchase likelihood for concepts 1-5), Q14, Q15-Q18, Q19, Q20 (multi-select, up to 2), Q21-Q26, Q30 (attention check). The real aytm export numbers questions differently (our Q1 is its Q6); `1_reference/crosswalk.csv` maps between the two.",
              "", "## Opening the CSVs in Excel", "",
              "Files written from 2026-09-12 on start with a UTF-8 byte-order mark, so double-clicking opens them with the right characters. If en dashes show up as odd symbols, the file predates that: run add_bom.py on the run folder, or import with Data > Get Data > From Text/CSV and set File Origin to 65001: Unicode (UTF-8). Multi-select cells contain | between the chosen options.", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--keeper-run", type=Path, default=None, help="copy this run's questions.csv to 1_reference/ (left alone otherwise)")
    parser.add_argument("--crosswalk", type=Path, default=None, help="copy this crosswalk to 1_reference/")
    args = parser.parse_args(argv)
    assets = args.assets.resolve()
    if not assets.is_dir():
        parser.error(f"{assets} is not a directory")
    reference = assets / "1_reference"
    if args.keeper_run is not None:
        if not (args.keeper_run / "questions.csv").is_file():
            parser.error(f"{args.keeper_run} has no questions.csv")
        reference.mkdir(exist_ok=True)
        shutil.copyfile(args.keeper_run / "questions.csv", reference / "questions.csv")
        print(f"1_reference/questions.csv <- {args.keeper_run}")
    if args.crosswalk is not None:
        reference.mkdir(exist_ok=True)
        shutil.copyfile(args.crosswalk, reference / "crosswalk.csv")
    text = render_start_here(assets=assets, keeper_run=args.keeper_run, today=datetime.now(timezone.utc).date().isoformat())
    (assets / "START_HERE.md").write_text(text, encoding="utf-8")
    print(f"START_HERE.md -> {assets / 'START_HERE.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
