"""Write START_HERE.md at the top of the shared folder and copy the codebook and crosswalk there.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/write_start_here.py --assets ../SyntheticResponderLab-Assets [--crosswalk <crosswalk.csv>]
"""

from __future__ import annotations

import argparse
import csv
import shutil
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PERSONA_SETS = OrderedDict([
    ("600_persona", "the PLAIN draw: 600 California owner-occupied detached single-family households, income $100k+, householder 30-65, drawn at random from the Census (ACS PUMS 2024 5-year, seed 20260825). Describes Neo's likely buyers; cannot be validated against the real survey."),
    ("match_600_persona", "the MATCHED draw: 600 households drawn nationally so age band x gender x income bracket x region reproduce the real 600 respondents (ACS PUMS 2024 1-year, seed 20260909, 199 cells, none short). This is the set compared against the real survey. Demographic agreement is by construction; only answer-level agreement is informative."),
])
REAL_DATA_DIR = "raw 600-participant dataset and a sample report from aytm"
# Everything else at the top level, listed only when present.
OTHER_ITEMS = OrderedDict([
    ("6_subset_of_dataset_plus_the_all_600_persona_data", "Yaza's Sept 16 matched 600 (outdoor-space screen at the draw) and its six 100-persona subsets S1-S6 (`panel_s*_ids.txt`, `subset_id_map.csv` map subset ids to full ids). `survey_runs/` holds the Sept 17 S1 runs; `real_comparison/` their comparisons, including the rescore on Dr. Lin's standard."),
    ("Sept24_real_vs_synthetic_experiments", "Yaza's Sept 23-24 S1 runs (income ablations, model families, response styles, the R018 and R018b mixed panels, the random control) with their comparisons and write-ups."),
    ("Sept25_review", "Minh's re-check of the Sept 23-24 results (`checkers.md`, `refutes.md`)."),
    ("Sept30_lin_standard_baselines", "the unstyled four-model mix (R018u) built from the Sept 23 runs, and the baselines for R020/R020b scored on Dr. Lin's standard."),
    ("DrLinSplit", "Dr. Lin's files as he sent them: `aytm_respondent_split_ids.csv` (300 cal / 300 val, seed 42; ids are row indexes, aytm_N = respondent row N), `item_split.csv` (13 calibration, 13 validation items), and the driver persona files (use `Regenerated Persona Files/`; the Sept 30 S1 file was the wrong 100 people)."),
    ("real_splits", "his split converted to Response IDs: `lin-seed42/` (`fit_ids.txt` = cal, `score_ids.txt` = val) is the scoring standard; `provisional-seed42/` is superseded."),
    ("Oct01_hybrid_R020", "R020 / R020b (2026-10-01): driver personas + drawn answers on the four-model mix, unstyled and styled. `survey_runs/` holds the 16 model runs, the 4 mixed panels (built with --keep-arm-order, same persona -> model deal as R018u / R018b) and the smoke tests; `real_comparison/` the scoring on Dr. Lin's standard and the spread diagnostics."),
    ("Oct02_separating_R021", "R021 (drawing only) and R021b (drivers only), 2026-10-02/03: the two halves of R020 run separately on the same four models and persona -> model deal. `real_comparison/` holds the scoring, the spread diagnostics and `attribution_R021.json`."),
    ("hybrid_personas", "run-ready hybrid persona files: Dr. Lin's four driver answers (copied from cal-half respondents) merged onto the team's persona file by import_driver_personas.py (`s1_drv.csv` = the team's S1, `s2lin_drv.csv` = his S2), each with a `.json` record of input hashes. Run only with --hybrid."),
    ("EXPERIMENT_LOG.md", "the lab notebook: every run, its result and its cost."),
    ("discussion", "`DISCUSSION_LOG.md` (week by week: what happened, decisions, next steps, the email archive), the emails and the meeting transcript."),
    ("NeoSmartLiving_App_Test_Log.xlsx", "the app test log; not an input to any run."),
])
RUN_FILES = OrderedDict([
    ("answers_long.csv", "one row per persona x question: run_id, model, repeat, seed, persona_id, respondent_id, question_id, question_type, answer, answer_json, is_fallback. Drop rows with is_fallback = true."),
    ("answers_wide.csv", "one row per persona, one column per question id, plus n_fallback and all_live. The file to load for analysis."),
    ("questions.csv", "the codebook for this run (identical to the top-level copy); has a preamble column when the survey reader carried stimulus text."),
    ("raw_responses.jsonl", "per persona: the model's raw text, serving host, model served, tokens, cost, attempts, finish reason."),
    ("generation_debug.json", "the engine's counters: executions, live vs fabricated answers, request errors."),
    ("prompt_sample.txt", "the exact prompt sent for the first persona."),
    ("summary.md", "Q1/Q2/Q6/Q14 answer shares, Q30 attention-check pass rate, Q21/Q22 agreement with the persona's exact age and income."),
    ("manifest.json", "everything needed to reproduce: sha256 of inputs and outputs, settings, seed, counts, tokens, cost, guardrail verdict, git commit."),
])


def read_index(index_path: Path) -> List[Dict[str, str]]:
    with open(index_path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def classify_runs(survey_runs: Path) -> Dict[str, List[Dict[str, Any]]]:
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


def pick_keeper_run(assets: Path, runs_by_set: Dict[str, Dict[str, List[Dict[str, Any]]]], explicit: Optional[Path]) -> Optional[Path]:
    if explicit is not None:
        if not (explicit / "questions.csv").is_file():
            raise FileNotFoundError(f"{explicit} has no questions.csv")
        return explicit
    for set_name in PERSONA_SETS:
        for entry in runs_by_set.get(set_name, {}).get("keepers", []):
            candidate = assets / set_name / "survey_runs" / entry["folder"]
            if (candidate / "questions.csv").is_file():
                return candidate
    return None


def _table(header: List[str], rows: List[List[str]]) -> List[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def render_start_here(*, runs_by_set: Dict[str, Dict[str, List[Dict[str, Any]]]], keeper_run: Optional[Path], crosswalk_present: bool, today: str,
                      present: Optional[Set[str]] = None) -> str:
    keeper_name = keeper_run.name if keeper_run else "(no keeper run found)"
    crosswalk_note = "Present." if crosswalk_present else "Not yet present: produced by compare_real.py; pass it to write_start_here.py --crosswalk."
    lines: List[str] = ["# START HERE — Neo Smart Living synthetic survey runs", "",
                        f"Updated {today} by research/neo_persona_set/phase3/write_start_here.py. Edit the script, not this file.", "",
                        "## What is at the top level", ""]
    top = [["`START_HERE.md`", "this file"],
           ["`questions.csv`", f"the codebook: the 39 answer items the synthetic respondents saw (question_id, question_type, min/max, options, text, preamble). Copied from keeper run `{keeper_name}`."],
           ["`crosswalk.csv`", f"our question_id next to the real survey's column, with notes on option differences. {crosswalk_note}"]]
    top += [[f"`{name}/`", description] for name, description in PERSONA_SETS.items()]
    top += [[f"`{REAL_DATA_DIR}/`", "the real respondents. Only compare_real.py reads it; the runner refuses any path containing aytm or survey-760085."]]
    top += [[f"`{name}`" if "." in name else f"`{name}/`", description] for name, description in OTHER_ITEMS.items() if name in (present or set())]
    lines += _table(["Item", "What it is"], top)
    lines += ["", "## How to score (from 2026-09-30)", "",
              "Dr. Lin's calibration / validation split is the standard. Score on his 13 validation items against his 300 held-out respondents:",
              "`compare_real.py --items lin13-validation --real-ids real_splits/lin-seed42/score_ids.txt`. Anything fitted to real answers (driver donors, adjustments) uses only `real_splits/lin-seed42/fit_ids.txt` and the calibration items.",
              "Hybrid runs (persona files with driver answers copied from real respondents) carry `hybrid` in the folder name and `persona_kind: hybrid` in the manifest; they are never scored on the four driver questions.",
              "Read rank agreement (mean_spearman) and top-answer match first, with the random control alongside; mean TV alone can be beaten by random answers."]
    lines += ["", "## Inside a persona-set folder", "",
              "- `phase1_interview_<set>.csv` — the 600 personas, 49 columns: 7 bucket fields, six blank classifier columns, 21 exact Census fields, name, 14 story_* columns. Names are random and carry no information.",
              "- `phase1_method_<set>.txt` — how the set was drawn, the screens, the bias controls.",
              "- `survey_runs/` — one folder per run, `index.csv` (one row per run incl. smoke and failed runs) and `cross_run_summary.md`.",
              "- `real_comparison/<stamp>/` (matched set) — question-by-question comparison with the real 600; start with comparison_by_question.md.",
              "",
              "Known issue in the matched persona file: age_bucket and income_bucket carry the plain draw's labels and contradict the exact values on many rows; home_type is a constant; county is blank for national rows. The runner derives the bucket labels from the exact values before prompting (the manifest counts the rows). lint_personas.py reports all of this.",
              "", "## Run folder names", "", "`<timestamp>_<model>_r<repeat>[_n<limit>|_p<panel>][_<tag>][_failed]`", "",
              "- timestamp: start time in UTC, 20260910T014617Z = 2026-09-10 01:46:17 UTC.",
              "- model: the OpenRouter model without the vendor prefix (deepseek-v4-pro-0813, qwen3.7-plus).",
              "- r1, r2: repeat number; each repeat uses seed 20260909 * 10 + repeat with temperature 0.2.",
              "- n5: only the first 5 personas (a smoke test). p150: a fixed panel chosen by select_panel.py.",
              "- tag: free text given at run time (matched, smoke, smoke-noreason).",
              "- _failed: the run tripped a guardrail. Kept for audit, never a keeper.",
              "", "## The eight files in every run folder", ""]
    lines += _table(["File", "What it holds"], [[f"`{name}`", text] for name, text in RUN_FILES.items()])
    lines += ["", "## Which runs to use", "", "A keeper is a completed run over all 600 personas that passed the guardrails. Smoke runs (_n5) and _failed runs are kept only for audit.", ""]
    for set_name in PERSONA_SETS:
        runs = runs_by_set.get(set_name)
        if runs is None:
            continue
        lines += [f"### {set_name} — keepers", ""]
        keepers = [[e["folder"], e.get("model", ""), e.get("repeat", ""), e.get("respondents", ""), e.get("fallback_answers", ""), e.get("usd_reported", "")] for e in runs["keepers"]]
        lines += _table(["run", "model", "repeat", "respondents", "fabricated answers", "usd (reported)"], keepers) if keepers else ["(none)"]
        lines += ["", f"### {set_name} — smoke and failed (ignore for analysis)", ""]
        others = [[e["folder"], e["why"]] for e in runs["other"]]
        lines += _table(["folder", "why"], others) if others else ["(none)"]
        lines.append("")
    lines += ["## Question ids", "",
              "39 items in survey order: S3 (screener), Q0A, Q0B, Q1, Q2, Q3, Q5_1-Q5_7 (the seven rows of the barrier matrix), Q6, Q7, Q9A/Q9B ... Q13A/Q13B (appeal and purchase likelihood for concepts 1-5), Q14, Q15-Q18, Q19, Q20 (multi-select, up to 2), Q21-Q26, Q30 (attention check). The real aytm export numbers questions differently (our Q1 is its Q6); crosswalk.csv maps between the two.",
              "", "## Opening the CSVs in Excel", "",
              "Files written from 2026-09-12 on start with a UTF-8 byte-order mark, so double-clicking opens them with the right characters. If en dashes show up as odd symbols, the file predates that: run add_bom.py on the run folder, or import with Data > Get Data > From Text/CSV and set File Origin to 65001: Unicode (UTF-8). Multi-select cells contain | between the chosen options.", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--keeper-run", type=Path, default=None)
    parser.add_argument("--crosswalk", type=Path, default=None)
    args = parser.parse_args(argv)
    assets = args.assets.resolve()
    if not assets.is_dir():
        parser.error(f"{assets} is not a directory")
    runs_by_set = {name: classify_runs(assets / name / "survey_runs") for name in PERSONA_SETS if (assets / name).is_dir()}
    keeper_run = pick_keeper_run(assets, runs_by_set, args.keeper_run)
    if keeper_run is not None:
        shutil.copyfile(keeper_run / "questions.csv", assets / "questions.csv")
        print(f"questions.csv <- {keeper_run}")
    crosswalk_present = (assets / "crosswalk.csv").is_file()
    if args.crosswalk is not None:
        shutil.copyfile(args.crosswalk, assets / "crosswalk.csv")
        crosswalk_present = True
    text = render_start_here(runs_by_set=runs_by_set, keeper_run=keeper_run, crosswalk_present=crosswalk_present, today=datetime.now(timezone.utc).date().isoformat(),
                             present={child.name for child in assets.iterdir()})
    (assets / "START_HERE.md").write_text(text, encoding="utf-8")
    print(f"START_HERE.md -> {assets / 'START_HERE.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
