"""Build the preloaded survey-run demo from a saved research run. Synthetic data only.

    .venv/bin/python scripts/build_demo_survey_fixture.py \
        --answers-long "<Assets>/5_experiments/2026-10-02_R021_drawing_only_vs_drivers_only/survey_runs/<...>_mixed-panel_r1_s1-R021-draw-mixed/answers_long.csv" \
        --personas "<Assets>/4_persona_sets/matched_600_v2_S1-S6_2026-09-16/phase1_interview_matched600_s1.csv" \
        --run-label "R021 r1 (drawing only, four-model mix, S1)" --run-date 2026-10-03 \
        --out src/services/demo_survey_fixture.json.gz
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AGE_BANDS: List[Tuple[int, int, str]] = [(0, 17, "under 18"), (18, 24, "18-24"), (25, 29, "25-29"), (30, 34, "30-34"),
                                         (35, 44, "35-44"), (45, 54, "45-54"), (55, 64, "55-64"), (65, 200, "65+")]
INCOME_BANDS: List[Tuple[int, int, str]] = [(0, 24_999, "<$25k"), (25_000, 49_999, "$25k-$50k"), (50_000, 74_999, "$50k-$75k"),
                                            (75_000, 99_999, "$75k-$100k"), (100_000, 149_999, "$100k-$150k"),
                                            (150_000, 199_999, "$150k-$200k"), (200_000, 299_999, "$200k-$300k"),
                                            (300_000, 499_999, "$300k-$500k"), (500_000, 10**12, "$500k+")]
PERSONA_FIELDS = ["persona_id", "age_bucket", "income_bucket", "household_size_bucket", "ownership", "home_type", "work_mode",
                  "lifestyle_tags", "likely_use_case", "likely_barrier", "segment_label", "affordability_pressure"]
DRIVER_COLUMNS = {"prior_consideration_of_backyard_unit", "outdoor_recreation_frequency", "member_of_outdoor_club",
                  "most_likely_use_for_a_backyard_unit"}


def _refuse(message: str) -> None:
    print(f"REFUSED: {message}", file=sys.stderr)
    raise SystemExit(3)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _band(value: Optional[str], bands: List[Tuple[int, int, str]]) -> Optional[str]:
    try:
        number = int(float(value or ""))
    except ValueError:
        return None
    return next((label for low, high, label in bands if low <= number <= high), None)


def _clean(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    return text or None


def _is_fallback(row: Dict[str, str]) -> bool:
    """A placeholder row, not a model answer. A missing is_fallback column counts as false."""
    return (row.get("is_fallback") or "").strip().lower() == "true"


def persona_from_row(row: Dict[str, str]) -> Dict[str, object]:
    persona: Dict[str, object] = {field: _clean(row.get(field)) for field in PERSONA_FIELDS}
    persona["age_bucket"] = _band(row.get("exact_age"), AGE_BANDS) or persona["age_bucket"]
    persona["income_bucket"] = _band(row.get("exact_household_income"), INCOME_BANDS) or persona["income_bucket"]
    size = _clean(row.get("household_size"))
    persona["household_size_bucket"] = persona["household_size_bucket"] or (f"{size} person(s)" if size else None)
    persona["lifestyle_tags"] = [tag.strip() for tag in (row.get("lifestyle_tags") or "").split(";") if tag.strip()]
    return persona


def build_fixture(answers_long: Path, personas_csv: Path, *, run_label: str, run_date: str) -> dict:
    for path in (answers_long, personas_csv):
        if "aytm" in str(Path(path).resolve()).lower():
            _refuse(f"{path} looks like real-respondent material")
    with open(personas_csv, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        drivers = [c for c in (reader.fieldnames or []) if c in DRIVER_COLUMNS or c.startswith("driver_")]
        if drivers:
            _refuse(f"{personas_csv} carries driver columns {drivers}; the demo is synthetic only")
        persona_rows = list(reader)
    answers: Dict[str, Dict[str, object]] = {}
    models: Dict[str, str] = {}
    question_ids: List[str] = []
    skipped_fallback_rows = 0
    with open(answers_long, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if _is_fallback(row):
                skipped_fallback_rows += 1
                continue
            pid, qid = row["persona_id"], row["question_id"]
            if qid not in question_ids:
                question_ids.append(qid)
            models[pid] = row["model"]
            answers.setdefault(pid, {})[qid] = json.loads(row["answer_json"]) if row.get("answer_json") else row["answer"]
    respondents = []
    for row in persona_rows:
        pid = row["persona_id"]
        if pid not in answers:
            continue
        respondents.append({"respondent_id": f"RESP_{len(respondents) + 1:03d}", "model": models[pid],
                            "persona": persona_from_row(row), "answers": answers[pid]})
    return {
        "source": {"run_label": run_label, "run_date": run_date, "answers_file": Path(answers_long).name,
                   "answers_sha256": _sha256(Path(answers_long)), "personas_sha256": _sha256(Path(personas_csv)),
                   "skipped_fallback_rows": skipped_fallback_rows},
        "question_ids": question_ids,
        "models_used": sorted(set(models.values())),
        "respondents": respondents,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers-long", type=Path, required=True)
    parser.add_argument("--personas", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    fixture = build_fixture(args.answers_long, args.personas, run_label=args.run_label, run_date=args.run_date)
    args.out.write_bytes(gzip.compress(json.dumps(fixture, ensure_ascii=False).encode("utf-8"), mtime=0))
    print(f"wrote {len(fixture['respondents'])} respondents x {len(fixture['question_ids'])} questions to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
