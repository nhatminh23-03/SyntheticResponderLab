"""Compare synthetic survey runs with the real AYTM survey, question by question. Fully offline.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/compare_real.py \\
        --real "../SyntheticResponderLab-Assets/2_real_data_aytm/survey-760085-2026-03-25-raw-data.csv" \\
        --runs <run_dir> [<run_dir> ...] --out ../SyntheticResponderLab-Assets/5_experiments/2026-09-10_first_full_600_runs/matched_600_v1/real_comparison/<stamp>

For every run x mapped question the answer categories are aligned through crosswalk.CROSSWALK, the
real and synthetic distributions are computed on the shared categories (off-list answers on either
side are counted and reported), and metrics.py supplies distances, rank checks and tests.
Outputs: comparison_long.csv, comparison_options.csv, comparison_summary.csv,
comparison_by_question.md, unmapped.md, crosswalk.csv, manifest.json. Nothing is ever written
next to the real file.

--items picks which questions count toward the summary (a named set from item_sets.py, e.g.
lin13-validation, or a file of question ids); the others are still compared and reported, marked
scored=false. --real-ids scores against only the listed real respondents (a file of AYTM Response
IDs, e.g. the score half from make_real_split.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import crosswalk  # noqa: E402
import filter_qualified  # noqa: E402
import item_sets  # noqa: E402
import metrics  # noqa: E402
import realdata  # noqa: E402

SCRIPT_PATH = "research/neo_persona_set/phase3/compare_real.py"
STATUS_OK = "ok"
STATUS_UNMAPPED = "unmapped"
STATUS_REAL_MISSING = "real_column_missing"
STATUS_OURS_MISSING = "our_question_missing"
STATUS_NO_DATA = "no_data"
CSV_ENCODING = "utf-8-sig"

LONG_COLUMNS = [
    "run_id", "run_label", "model", "our_id", "real_key", "kind", "status", "scored", "n_real", "n_synth",
    "n_real_off_list", "n_synth_off_list", "real_off_list_share", "synth_off_list_share", "n_categories",
    "categories", "real_shares", "synth_shares", "tv", "js", "spearman", "top_real", "top_synth", "top_match",
    "max_abs_share_diff", "mean_real", "mean_synth", "mean_diff", "chi2", "chi2_df", "chi2_p", "close", "notes",
]
OPTIONS_COLUMNS = [
    "run_id", "run_label", "our_id", "real_key", "kind", "category", "real_count", "real_n", "real_share",
    "synth_count", "synth_n", "synth_share", "diff", "z", "z_p",
]
SUMMARY_COLUMNS = [
    "run_id", "run_label", "model", "n_synth_total", "n_synth_after_filter", "n_dropped_outdoor", "n_fallback_blanked",
    "questions_compared", "questions_close", "share_close", "mean_tv", "median_tv", "mean_js", "share_top_match",
    "mean_spearman", "likert_questions", "mean_abs_mean_diff", "questions_chi2_p_below_05", "item_set", "n_real_respondents",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_of_file(path: Path) -> str:
    return filter_qualified.sha256_of_file(path)


def git_info() -> Dict[str, Any]:
    def _run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ""

    return {"commit": _run("rev-parse", "HEAD"), "branch": _run("rev-parse", "--abbrev-ref", "HEAD"), "dirty": bool(_run("status", "--porcelain", "--untracked-files=no"))}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def num(value: Any, digits: int = 4) -> str:
    """CSV cell for a number: blank for None/NaN, rounded otherwise; bools as true/false."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if math.isnan(value) else ("inf" if math.isinf(value) else f"{value:.{digits}f}")
    return str(value)


def pct(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.1%}"


def model_slug(model: str) -> str:
    return model.split("/")[-1].replace(":", "-")


@dataclass
class RunData:
    run_id: str
    model: str
    repeat: str
    run_dir: Path
    questions: Dict[str, crosswalk.Question]
    rows: List[Dict[str, str]]
    n_total: int
    n_dropped_outdoor: int
    n_fallback_blanked: int
    hashes: Dict[str, str]
    label: str = ""


def load_fallback_keys(path: Path) -> Set[Any]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return {(row["persona_id"], row["question_id"]) for row in csv.DictReader(handle) if row.get("is_fallback") == "true"}


def blank_fallbacks(rows: List[Dict[str, str]], question_ids: List[str], keys: Set[Any]) -> int:
    blanked = 0
    for row in rows:
        for question_id in question_ids:
            if (row["persona_id"], question_id) in keys:
                row[question_id] = ""
                blanked += 1
    return blanked


def load_run(run_dir: Path, *, require_outdoor_space: bool, exclude_fallback: bool) -> RunData:
    questions = crosswalk.load_questions(run_dir / "questions.csv")
    _, rows = filter_qualified.read_csv_rows(run_dir / "answers_wide.csv")
    n_total = len(rows)
    if require_outdoor_space:
        rows = [row for row in rows if filter_qualified.is_qualified(row.get(filter_qualified.SCREENER_ID))]
    blanked = 0
    if exclude_fallback:
        blanked = blank_fallbacks(rows, list(questions), load_fallback_keys(run_dir / "answers_long.csv"))
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    first = rows[0] if rows else {}
    hashes = {name: sha256_of_file(run_dir / name) for name in ("answers_wide.csv", "questions.csv") if (run_dir / name).exists()}
    return RunData(
        run_id=first.get("run_id") or manifest.get("run_id") or run_dir.name,
        model=first.get("model") or (manifest.get("model") or {}).get("requested") or "?",
        repeat=first.get("repeat") or "", run_dir=run_dir, questions=questions, rows=rows, n_total=n_total,
        n_dropped_outdoor=n_total - len(rows), n_fallback_blanked=blanked, hashes=hashes,
    )


def assign_labels(runs: List[RunData]) -> None:
    labels = [f"{model_slug(run.model)} r{run.repeat}".strip() for run in runs]
    for run, label in zip(runs, labels):
        run.label = label if labels.count(label) == 1 else run.run_id


@dataclass
class CategorySpec:
    labels: List[str]
    lookup: Dict[str, str]


def build_spec(qmap: crosswalk.QuestionMap, question: crosswalk.Question) -> CategorySpec:
    if qmap.kind == "likert":
        low, high = question.min_value or 1, question.max_value or 5
        labels = [str(value) for value in range(low, high + 1)]
        return CategorySpec(labels, {label: label for label in labels})
    if qmap.kind == "derived_binary":
        labels = ["Yes", "No"]
    elif qmap.kind == "income_band":
        labels = list(crosswalk.INCOME_BANDS)
    else:
        labels = []
        for option in question.options:
            mapped = qmap.map_our_label(option)
            if mapped is not None and mapped not in labels:
                labels.append(mapped)
    return CategorySpec(labels, {qmap.normalize(label): label for label in labels})


def synth_categorizer(qmap: crosswalk.QuestionMap, spec: CategorySpec) -> Callable[[str], Optional[str]]:
    def categorize(raw: str) -> Optional[str]:
        if qmap.kind == "likert":
            value = realdata.likert_label_to_int(raw)
            return None if value is None else spec.lookup.get(str(value))
        mapped = qmap.map_our_label(raw)
        return None if mapped is None else spec.lookup.get(qmap.normalize(mapped))
    return categorize


def real_categorizer(qmap: crosswalk.QuestionMap, spec: CategorySpec) -> Callable[[str], Optional[str]]:
    def categorize(raw: str) -> Optional[str]:
        if qmap.kind == "likert":
            value = realdata.likert_label_to_int(raw)
            return None if value is None else spec.lookup.get(str(value))
        if qmap.kind == "age_bin":
            try:
                return crosswalk.age_bucket_for(int(float(raw)), spec.labels)
            except ValueError:
                return None
        return spec.lookup.get(qmap.normalize(qmap.map_real_label(raw)))
    return categorize


@dataclass
class Extract:
    labels: List[str]
    counts: Dict[str, int]
    n: int = 0
    n_off_list: int = 0
    n_missing: int = 0
    n_picks: int = 0

    def shares(self) -> Dict[str, float]:
        return {label: (self.counts[label] / self.n if self.n else 0.0) for label in self.labels}

    def distribution(self) -> Dict[str, float]:
        return {label: (self.counts[label] / self.n_picks if self.n_picks else 0.0) for label in self.labels}

    def off_list_share(self) -> float:
        base = self.n_picks + self.n_off_list
        return self.n_off_list / base if base else 0.0

    def mean(self) -> float:
        return sum(int(label) * count for label, count in self.counts.items()) / self.n if self.n else metrics.NAN


def extract_single(values: List[Optional[str]], labels: List[str], categorize: Callable[[str], Optional[str]]) -> Extract:
    extract = Extract(labels, {label: 0 for label in labels})
    for raw in values:
        if raw is None or not str(raw).strip():
            extract.n_missing += 1
            continue
        label = categorize(str(raw).strip())
        if label is None:
            extract.n_off_list += 1
            continue
        extract.counts[label] += 1
        extract.n += 1
        extract.n_picks += 1
    return extract


def extract_multi(picks: List[Set[str]], labels: List[str], categorize: Callable[[str], Optional[str]]) -> Extract:
    extract = Extract(labels, {label: 0 for label in labels})
    for chosen in picks:
        if not chosen:
            extract.n_missing += 1
            continue
        extract.n += 1
        for raw in chosen:
            label = categorize(raw)
            if label is None:
                extract.n_off_list += 1
            else:
                extract.counts[label] += 1
                extract.n_picks += 1
    return extract


def derive_binary(selected_ids: Set[str], qmap: crosswalk.QuestionMap) -> Optional[str]:
    if not selected_ids:
        return None
    if any(sub_id not in qmap.real_map for sub_id in selected_ids):
        return "Yes"
    return qmap.real_map[sorted(selected_ids)[0]]


def extract_real(real: realdata.RealSurvey, qmap: crosswalk.QuestionMap, spec: CategorySpec) -> Optional[Extract]:
    categorize = real_categorizer(qmap, spec)
    key = qmap.real_key or ""
    if qmap.kind in ("multi", "derived_binary"):
        if not realdata.multiselect_columns(real.columns, key):
            return None
        if qmap.kind == "multi":
            return extract_multi(realdata.multiselect_block(real.rows, key), spec.labels, categorize)
        derived = [derive_binary(ids, qmap) for ids in realdata.multiselect_sub_ids(real.rows, key)]
        return extract_single(derived, spec.labels, categorize)
    column = real.find(key)
    if column is None:
        return None
    return extract_single([row[column] for row in real.rows], spec.labels, categorize)


def extract_synth(run: RunData, qmap: crosswalk.QuestionMap, spec: CategorySpec) -> Extract:
    categorize = synth_categorizer(qmap, spec)
    answers = [row.get(qmap.our_id, "") for row in run.rows]
    if qmap.kind == "multi":
        picks = [{part.strip() for part in answer.split("|") if part.strip()} for answer in answers]
        return extract_multi(picks, spec.labels, categorize)
    return extract_single(answers, spec.labels, categorize)


@dataclass
class QuestionResult:
    qmap: crosswalk.QuestionMap
    run: RunData
    status: str
    spec: Optional[CategorySpec] = None
    real: Optional[Extract] = None
    synth: Optional[Extract] = None
    stats: Dict[str, Any] = field(default_factory=dict)


def score(qmap: crosswalk.QuestionMap, real_x: Extract, synth_x: Extract, close_tv: float) -> Dict[str, Any]:
    p, q = real_x.distribution(), synth_x.distribution()
    real_shares, synth_shares = real_x.shares(), synth_x.shares()
    stats: Dict[str, Any] = {
        "tv": metrics.tv_distance(p, q), "js": metrics.js_divergence(p, q),
        "spearman": metrics.spearman(list(p.values()), list(q.values())),
        "top_real": metrics.top_option(p), "top_synth": metrics.top_option(q), "top_match": metrics.top_option_match(p, q),
        "max_abs_share_diff": max(abs(real_shares[label] - synth_shares[label]) for label in real_x.labels),
        "mean_real": metrics.NAN, "mean_synth": metrics.NAN, "mean_diff": metrics.NAN,
    }
    if qmap.kind == "likert":
        stats["mean_real"], stats["mean_synth"] = real_x.mean(), synth_x.mean()
        stats["mean_diff"] = stats["mean_synth"] - stats["mean_real"]
    stats["chi2"], stats["chi2_df"], stats["chi2_p"] = metrics.chi2_gof(synth_x.counts, p)
    stats["close"] = stats["tv"] <= close_tv
    return stats


def compare_one(real: realdata.RealSurvey, run: RunData, qmap: crosswalk.QuestionMap, close_tv: float) -> QuestionResult:
    if qmap.kind == "none":
        return QuestionResult(qmap, run, STATUS_UNMAPPED)
    question = run.questions.get(qmap.our_id)
    if question is None:
        return QuestionResult(qmap, run, STATUS_OURS_MISSING)
    spec = build_spec(qmap, question)
    real_x = extract_real(real, qmap, spec)
    if real_x is None:
        return QuestionResult(qmap, run, STATUS_REAL_MISSING, spec)
    synth_x = extract_synth(run, qmap, spec)
    if real_x.n == 0 or synth_x.n == 0:
        return QuestionResult(qmap, run, STATUS_NO_DATA, spec, real_x, synth_x)
    return QuestionResult(qmap, run, STATUS_OK, spec, real_x, synth_x, score(qmap, real_x, synth_x, close_tv))


def scored_maps(items: Optional[Sequence[str]] = None) -> List[crosswalk.QuestionMap]:
    """The crosswalk with `scored` narrowed to `items`; every entry is kept so it is still reported."""
    if items is None:
        return list(crosswalk.CROSSWALK)
    wanted = set(items)
    return [replace(qmap, scored=qmap.scored and qmap.our_id in wanted) for qmap in crosswalk.CROSSWALK]


def compare_runs(real: realdata.RealSurvey, runs: List[RunData], close_tv: float, items: Optional[Sequence[str]] = None) -> List[QuestionResult]:
    return [compare_one(real, run, qmap, close_tv) for qmap in scored_maps(items) for run in runs]


def long_row(result: QuestionResult) -> Dict[str, str]:
    qmap, run, stats = result.qmap, result.run, result.stats
    row = {column: "" for column in LONG_COLUMNS}
    row.update({"run_id": run.run_id, "run_label": run.label, "model": run.model, "our_id": qmap.our_id, "real_key": qmap.real_key or "",
                "kind": qmap.kind, "status": result.status, "scored": num(qmap.scored), "notes": qmap.notes})
    if result.real is not None and result.synth is not None:
        real_x, synth_x = result.real, result.synth
        row.update({
            "n_real": str(real_x.n), "n_synth": str(synth_x.n), "n_real_off_list": str(real_x.n_off_list), "n_synth_off_list": str(synth_x.n_off_list),
            "real_off_list_share": num(real_x.off_list_share()), "synth_off_list_share": num(synth_x.off_list_share()),
            "n_categories": str(len(real_x.labels)), "categories": "|".join(real_x.labels),
            "real_shares": "|".join(num(v) for v in real_x.shares().values()), "synth_shares": "|".join(num(v) for v in synth_x.shares().values()),
        })
    for key, value in stats.items():
        row[key] = num(value)
    return row


def option_rows(result: QuestionResult) -> List[Dict[str, str]]:
    if result.status != STATUS_OK or result.real is None or result.synth is None:
        return []
    real_x, synth_x = result.real, result.synth
    rows: List[Dict[str, str]] = []
    for label in real_x.labels:
        real_count, synth_count = real_x.counts[label], synth_x.counts[label]
        z, z_p = metrics.two_proportion_z(real_count, real_x.n, synth_count, synth_x.n)
        rows.append({"run_id": result.run.run_id, "run_label": result.run.label, "our_id": result.qmap.our_id, "real_key": result.qmap.real_key or "",
                     "kind": result.qmap.kind, "category": label, "real_count": str(real_count), "real_n": str(real_x.n), "real_share": num(real_count / real_x.n),
                     "synth_count": str(synth_count), "synth_n": str(synth_x.n), "synth_share": num(synth_count / synth_x.n),
                     "diff": num(synth_count / synth_x.n - real_count / real_x.n), "z": num(z), "z_p": num(z_p, 6)})
    return rows


def summarize_run(run: RunData, results: List[QuestionResult], *, item_set: str = "all", n_real_respondents: Optional[int] = None) -> Dict[str, Any]:
    scored = [r for r in results if r.run is run and r.status == STATUS_OK and r.qmap.scored]
    likert = [r for r in scored if r.qmap.kind == "likert"]
    spearmans = [r.stats["spearman"] for r in scored if not math.isnan(r.stats["spearman"])]
    count = len(scored)
    return {
        "run_id": run.run_id, "run_label": run.label, "model": run.model, "n_synth_total": run.n_total, "n_synth_after_filter": len(run.rows),
        "n_dropped_outdoor": run.n_dropped_outdoor, "n_fallback_blanked": run.n_fallback_blanked, "questions_compared": count,
        "questions_close": sum(1 for r in scored if r.stats["close"]), "share_close": (sum(1 for r in scored if r.stats["close"]) / count) if count else metrics.NAN,
        "mean_tv": metrics.mean([r.stats["tv"] for r in scored]), "median_tv": metrics.median([r.stats["tv"] for r in scored]),
        "mean_js": metrics.mean([r.stats["js"] for r in scored]), "share_top_match": (sum(1 for r in scored if r.stats["top_match"]) / count) if count else metrics.NAN,
        "mean_spearman": metrics.mean(spearmans), "likert_questions": len(likert), "mean_abs_mean_diff": metrics.mean([abs(r.stats["mean_diff"]) for r in likert]),
        "questions_chi2_p_below_05": sum(1 for r in scored if not math.isnan(r.stats["chi2_p"]) and r.stats["chi2_p"] < 0.05),
        "item_set": item_set, "n_real_respondents": "" if n_real_respondents is None else n_real_respondents,
    }


def write_csv(path: Path, header: List[str], rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding=CSV_ENCODING) as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: (row[key] if isinstance(row.get(key), str) else num(row.get(key))) for key in header})


def _shares_table(qmap: crosswalk.QuestionMap, ok: List[QuestionResult]) -> List[str]:
    real_x = ok[0].real
    assert real_x is not None
    real_shares = real_x.shares()
    header = f"| category | real (n={real_x.n}) | " + " | ".join(f"{r.run.label} (n={r.synth.n})" for r in ok if r.synth) + " |"
    lines = [header, "| --- | --- |" + " --- |" * len(ok)]
    for label in real_x.labels:
        cells = [pct(real_shares[label])] + [pct(r.synth.shares()[label]) for r in ok if r.synth]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    off = [pct(real_x.off_list_share())] + [pct(r.synth.off_list_share()) for r in ok if r.synth]
    lines.append("| off-list share | " + " | ".join(off) + " |")
    if qmap.kind == "likert":
        means = [f"{real_x.mean():.2f}"] + [f"{r.synth.mean():.2f}" for r in ok if r.synth]
        lines.append("| mean (scale) | " + " | ".join(means) + " |")
    return lines


def _metrics_table(ok: List[QuestionResult], close_tv: float) -> List[str]:
    lines = ["| metric | " + " | ".join(r.run.label for r in ok) + " |", "| --- |" + " --- |" * len(ok)]
    rows = [
        ("TV distance", lambda s: f"{s['tv']:.3f}"), ("JS divergence (bits)", lambda s: f"{s['js']:.3f}"),
        ("Spearman on option shares", lambda s: "n/a" if math.isnan(s["spearman"]) else f"{s['spearman']:.2f}"),
        ("top option", lambda s: f"{s['top_synth']} ({'match' if s['top_match'] else 'real: ' + str(s['top_real'])})"),
        ("chi-square p", lambda s: "n/a" if math.isnan(s["chi2_p"]) else f"{s['chi2_p']:.3g}"),
        (f"close (TV <= {close_tv:.2f})", lambda s: "yes" if s["close"] else "no"),
    ]
    for name, render in rows:
        lines.append(f"| {name} | " + " | ".join(render(r.stats) for r in ok) + " |")
    return lines


def render_by_question(results: List[QuestionResult], close_tv: float) -> str:
    lines = ["# Real (AYTM) vs synthetic runs, question by question", "",
             "Shares are per respondent on the categories both surveys share; answers outside the shared list are reported as the off-list share and excluded before renormalizing. Multi-select shares are the share of respondents selecting each option; TV/JS/chi-square for multi-selects use the pick distribution.", ""]
    for entry in crosswalk.CROSSWALK:
        ok = [r for r in results if r.qmap.our_id == entry.our_id and r.status == STATUS_OK]
        if not ok:
            continue
        qmap = ok[0].qmap  # carries the scored flag for this comparison's item set
        text = ok[0].run.questions[qmap.our_id].text[:140]
        flag = "" if qmap.scored else " (report only)"
        lines += [f"## {qmap.our_id} vs real {qmap.real_key} ({qmap.kind}{flag})", "", text, "", *_shares_table(qmap, ok), "", *_metrics_table(ok, close_tv), ""]
        if qmap.notes:
            lines += [f"Notes: {qmap.notes}", ""]
    return "\n".join(lines) + "\n"


def render_unmapped(real: realdata.RealSurvey) -> str:
    lines = ["# Questions without a counterpart", "", "## Our questions with no real counterpart", "", "| our id | reason |", "| --- | --- |"]
    for qmap in crosswalk.CROSSWALK:
        if qmap.kind == "none":
            lines.append(f"| {qmap.our_id} | {qmap.notes} |")
    mapped = crosswalk.mapped_real_bases()
    survey_lines, meta_lines = [], []
    for code in real.base_codes():
        if code in mapped:
            continue
        columns = [c for c in real.columns if realdata.base_code(c) == code]
        text = real.header_text.get(columns[0], "").replace("\n", " ")[:110]
        target = survey_lines if realdata.split_code(code) else meta_lines
        target.append(f"| {code} | {len(columns)} | {text} |")
    lines += ["", "## Real survey items with no synthetic counterpart", "", "Q34.x is the Van Westendorp pricing module; Q4/Q5/Q13/Q14/Q17/Q20/Q23/Q26 are read-only stimulus screens; .OE columns are free text.", "", "| real code | columns | question text |", "| --- | --- | --- |", *survey_lines]
    lines += ["", "## Real metadata and demographic columns not compared", "", "| column | sub-columns | header |", "| --- | --- | --- |", *meta_lines]
    return "\n".join(lines) + "\n"


def observed_real_options(real: realdata.RealSurvey, qmap: crosswalk.QuestionMap) -> List[str]:
    key = qmap.real_key or ""
    if qmap.kind in ("multi", "derived_binary"):
        labels = []
        for column in realdata.multiselect_columns(real.columns, key):
            labels.append(next((row[column].strip() for row in real.rows if row[column].strip()), column.split("|")[1]))
        return labels
    column = real.find(key)
    if column is None:
        return []
    distinct = sorted({row[column].strip() for row in real.rows if row[column].strip()})
    if qmap.kind == "likert":
        distinct.sort(key=lambda label: realdata.likert_label_to_int(label) or 0)
    return distinct[:40]


def write_outputs(out_dir: Path, real: realdata.RealSurvey, runs: List[RunData], results: List[QuestionResult], args: argparse.Namespace) -> Dict[str, Path]:
    outputs = {name: out_dir / name for name in ("comparison_long.csv", "comparison_options.csv", "comparison_summary.csv", "comparison_by_question.md", "unmapped.md", "crosswalk.csv")}
    write_csv(outputs["comparison_long.csv"], LONG_COLUMNS, [long_row(r) for r in results])
    write_csv(outputs["comparison_options.csv"], OPTIONS_COLUMNS, [row for r in results for row in option_rows(r)])
    write_csv(outputs["comparison_summary.csv"], SUMMARY_COLUMNS,
              [summarize_run(run, results, item_set=args.item_set_name, n_real_respondents=real.n) for run in runs])
    outputs["comparison_by_question.md"].write_text(render_by_question(results, args.close_tv), encoding="utf-8")
    outputs["unmapped.md"].write_text(render_unmapped(real), encoding="utf-8")
    crosswalk.write_crosswalk_csv(outputs["crosswalk.csv"], our_options=crosswalk.our_options_from_questions(runs[0].questions),
                                  real_options={qmap.our_id: observed_real_options(real, qmap) for qmap in crosswalk.CROSSWALK if qmap.real_key})
    return outputs


def build_manifest(args: argparse.Namespace, real_path: Path, real: realdata.RealSurvey, runs: List[RunData], results: List[QuestionResult], outputs: Dict[str, Path]) -> Dict[str, Any]:
    git = git_info()
    status_counts: Dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    return {
        "created_at": utcnow().isoformat(),
        "script": {"path": SCRIPT_PATH, "git_commit": git["commit"], "git_branch": git["branch"], "git_dirty": git["dirty"], "python": sys.version.split()[0]},
        "real": {"path": str(real_path), "sha256": sha256_of_file(real_path), "n_rows": real.n, "n_rows_in_file": args.n_real_in_file,
                 "n_columns": len(real.columns),
                 "subset": None if args.real_ids is None else {"ids_file": str(args.real_ids), "sha256": sha256_of_file(Path(args.real_ids)), "n": real.n}},
        "items": {"set": args.item_set_name, "ids": list(args.item_ids), "n": len(args.item_ids)},
        "runs": [{"run_id": run.run_id, "run_label": run.label, "model": run.model, "repeat": run.repeat, "run_dir": str(run.run_dir), "sha256": run.hashes,
                  "n_total": run.n_total, "n_after_outdoor_filter": len(run.rows), "n_dropped_outdoor": run.n_dropped_outdoor, "n_fallback_blanked": run.n_fallback_blanked} for run in runs],
        "filters": {"require_outdoor_space": bool(args.require_outdoor_space), "screener_id": filter_qualified.SCREENER_ID, "exclude_fallback": bool(args.exclude_fallback)},
        "thresholds": {"close_tv": float(args.close_tv)},
        "crosswalk": {"entries": len(crosswalk.CROSSWALK), "mapped": sum(1 for q in crosswalk.CROSSWALK if q.kind != "none"),
                      "report_only": [q.our_id for q in crosswalk.CROSSWALK if not q.scored], "unmapped_ours": [q.our_id for q in crosswalk.CROSSWALK if q.kind == "none"]},
        "results_by_status": status_counts,
        "outputs": {name: sha256_of_file(path) for name, path in outputs.items()},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--real", type=Path, required=True, help="the AYTM raw-data CSV (two header rows)")
    parser.add_argument("--runs", type=Path, nargs="+", required=True, metavar="RUN_DIR")
    parser.add_argument("--out", type=Path, required=True, help="output folder (never inside the real-data folder)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--require-outdoor-space", dest="require_outdoor_space", action="store_true", default=True)
    group.add_argument("--keep-all", dest="require_outdoor_space", action="store_false")
    parser.add_argument("--close-tv", type=float, default=0.10)
    parser.add_argument("--exclude-fallback", action="store_true")
    parser.add_argument("--items", default=None, metavar="SET_OR_FILE",
                        help=f"questions that count toward the summary: one of {', '.join(item_sets.NAMED_SETS)}, or a file of question ids (default: every comparable question)")
    parser.add_argument("--real-ids", type=Path, default=None, metavar="FILE",
                        help="score against only these real respondents: a file of AYTM Response IDs, one per line")
    return parser


def hybrid_problem(run_dirs: List[Path], item_ids: List[str], real_ids: Optional[Path]) -> Optional[str]:
    """Why hybrid runs cannot be scored this way, or None.

    A hybrid persona carries four answers copied from a real respondent in the calibration half, so
    its runs are scored only against the held-out respondents (--real-ids) and never on the driver
    items, which would be graded on the answers they were given.
    """
    hybrid = []
    for run_dir in run_dirs:
        path = Path(run_dir) / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if manifest.get("persona_kind") == "hybrid":
            hybrid.append(Path(run_dir).name)
    if not hybrid:
        return None
    if real_ids is None:
        return f"hybrid runs {hybrid[:3]} must be scored on the held-out respondents only: pass --real-ids (the score half)"
    drivers = [item for item in item_ids if item in item_sets.LIN_DRIVERS]
    if drivers:
        return f"hybrid runs {hybrid[:3]} cannot be scored on the driver items {drivers}: their answers were copied in; pass --items without them"
    return None


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    real_path = Path(args.real).expanduser().resolve()
    if not real_path.is_file():
        print(f"--real {real_path} is not a file", file=sys.stderr)
        return 2
    out_dir = realdata.assert_outside_real_folder(args.out, real_path, "--out")
    run_dirs = [realdata.assert_outside_real_folder(path, real_path, "--runs") for path in args.runs]
    try:
        if args.items is None:
            args.item_set_name, args.item_ids = "all", [q.our_id for q in crosswalk.CROSSWALK if q.kind != "none" and q.scored]
        else:
            args.item_set_name, args.item_ids = item_sets.load_item_set(args.items)
        real = realdata.load_real_survey(real_path)
        args.n_real_in_file = real.n
        if args.real_ids is not None:
            real = realdata.subset_by_response_id(real, realdata.read_id_file(args.real_ids))
    except ValueError as error:
        print(f"compare_real: {error}", file=sys.stderr)
        return 2
    problem = hybrid_problem(run_dirs, args.item_ids, args.real_ids)
    if problem:
        print(f"compare_real: {problem}", file=sys.stderr)
        return 2
    runs = [load_run(path, require_outdoor_space=args.require_outdoor_space, exclude_fallback=args.exclude_fallback) for path in run_dirs]
    assign_labels(runs)
    results = compare_runs(real, runs, args.close_tv, None if args.items is None else args.item_ids)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = write_outputs(out_dir, real, runs, results, args)
    write_json(out_dir / "manifest.json", build_manifest(args, real_path, real, runs, results, outputs))
    print(f"real: {real.n} of {args.n_real_in_file} respondents, {len(real.columns)} columns; items: {args.item_set_name} ({len(args.item_ids)})")
    for run in runs:
        summary = summarize_run(run, results, item_set=args.item_set_name, n_real_respondents=real.n)
        print(f"{run.label:32s} n={len(run.rows):4d} compared={summary['questions_compared']:2d} close={summary['questions_close']:2d} "
              f"mean_tv={summary['mean_tv']:.3f} top_match={pct(summary['share_top_match'])} |mean diff|={summary['mean_abs_mean_diff']:.2f}")
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
