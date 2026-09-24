"""Run the whole 39-item instrument through TypeSafe's Jev classifier, on the S1 panel.

This replaces the three-question pilot. The headline metrics — mean total-variation distance to the
real 600, the share of questions close, the share whose top answer matches — are only defined over
the full instrument, so a partial run cannot be placed next to anything in the registry.

Jev is not a chat model. One request carries a `state` (the persona plus the product stimulus) and a
map of questions; each question is answered in isolation and comes back as a probability
distribution over its options rather than a single pick. Two consequences:

  * A stance formed on Q1 cannot leak into Q2, because the questions never share a generation.
    R007 found that leakage is real for chat models; here it is absent by construction.
  * Every persona yields a distribution per question. The discrete answer written to
    answers_wide.csv is the argmax, so the file is directly comparable to a chat run, and the full
    vector is kept alongside in probabilities.csv, because on Q1 the probability vector scored a
    distance of 0.256 against the real 600 where its own argmax scored 0.505.

Output matches the layout phase2/run_survey.py writes, so spread_diagnostics.py, compare_real.py and
score_vs_real_marginals.py read a Jev run with no adapter.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/jev_survey.py --run-tag s1-jev-full
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "phase2"))
import run_survey as chat_runner  # noqa: E402  the survey parser and the persona field lists

API_ENV = REPO_ROOT / "apps/api/.env"
DEFAULT_PERSONAS = HERE.parent / "out" / "phase1_interview_matched600_s1.csv"
DEFAULT_OUT = HERE.parent / "out" / "survey_runs"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"

# This interpreter has no system CA bundle wired into OpenSSL, so an unconfigured urlopen fails the
# handshake with CERTIFICATE_VERIFY_FAILED. certifi ships the bundle; falling back to the default
# context keeps the script working on a machine where OpenSSL is already configured.
try:
    import certifi

    SSL_CONTEXT: Optional[ssl.SSLContext] = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover - only on an interpreter without certifi
    SSL_CONTEXT = None
MODEL = "jev-latest"

# Persona fields sent as the state, kept in step with what the chat runner puts in the prompt so the
# two are comparable. Ablations drop members of these lists by name.
CENSUS_FIELDS = [
    "exact_age", "sex", "region", "state", "exact_household_income", "income_bucket",
    "household_size", "children_in_household", "household_type", "marital_status", "education",
    "occupation", "employment_status", "work_mode", "home_type", "tenure_detail", "bedrooms",
    "rooms", "year_built", "moved_in", "vehicles", "housing_cost_pct_of_income",
]
STORY_PREFIX = "story_"

# Q5's grid rows carry no per-row option labels; the scale is stated once in the question preamble as
# "1 = Would not reduce my likelihood at all, 5 = Would strongly reduce my likelihood". Repeating it
# here is what lets those seven items be asked as ScoreQuestions.
GRID_ANCHORS = (
    "Would not reduce my likelihood at all",
    "Would reduce my likelihood slightly",
    "Would reduce my likelihood moderately",
    "Would reduce my likelihood a lot",
    "Would strongly reduce my likelihood",
)


def load_key() -> str:
    key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not key and API_ENV.exists():
        for line in API_ENV.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit(f"TYPESAFE_API_KEY not set. Add it to {API_ENV}")
    return key


def build_state(persona: Dict[str, str], preambles: List[str],
                drop_census: set, drop_story: set) -> Dict[str, Any]:
    """The persona and the stimulus, as one state object.

    Jev has no question order, so the preambles that a chat respondent meets partway through the
    survey are all supplied up front as context. Every preamble in the instrument is included, which
    means the concept descriptions reach Jev exactly as they reach the chat models.
    """
    respondent: Dict[str, Any] = {}
    for field in CENSUS_FIELDS:
        if field in drop_census:
            continue
        value = (persona.get(field) or "").strip()
        if value:
            respondent[field] = value
    for column, raw in persona.items():
        if not column.startswith(STORY_PREFIX):
            continue
        key = column[len(STORY_PREFIX):]
        if key in drop_story:
            continue
        value = (raw or "").strip()
        if value:
            respondent[key] = value
    return {"stimulus": "\n\n".join(preambles), "respondent": respondent}


def build_questions(questions: List[Any]) -> Dict[str, Dict[str, Any]]:
    """Map the parsed instrument onto Jev's two question types.

    A likert item becomes a ScoreQuestion whose criteria are its five anchor labels, so the returned
    distribution is over 1-5 and lines up with what the chat runner records. Everything else becomes
    a ChoiceQuestion over its own option list. Q20 is multi-select and is asked as a single choice;
    its two highest-probability options are joined on write, matching the chat runner's format.

    The seven Q5 rows are a grid: the parser gives them min_value 1 and max_value 5 but an empty
    option list, because the scale sits in the question's own preamble rather than beside each row.
    They are the barrier-severity items and dropping them would cost a fifth of the instrument, so
    the anchors are supplied from GRID_ANCHORS, which repeats the wording of that preamble.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for question in questions:
        data = question.model_dump()
        options = list(data.get("options") or [])
        text = " ".join(str(data.get("text") or "").split())
        if data.get("question_type") == "likert":
            if len(options) != 5 and (data.get("min_value"), data.get("max_value")) == (1, 5):
                options = list(GRID_ANCHORS)
            if len(options) == 5:
                out[data["id"]] = {"type": "score", "instructions": text, "criteria": options}
                continue
        if options:
            out[data["id"]] = {"type": "choice", "instructions": text,
                               "criteria": {option: option for option in options}}
    return out


def ask(key: str, payload: Dict[str, Any], timeout: int, retries: int = 4) -> Dict[str, Any]:
    body = json.dumps(payload).encode()
    last: Optional[Exception] = None
    for attempt in range(retries):
        request = urllib.request.Request(
            ENDPOINT, data=body, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = error.read().decode()[:300]
            if error.code not in (408, 429) and error.code < 500:
                raise RuntimeError(f"HTTP {error.code}: {detail}") from error
            last = RuntimeError(f"HTTP {error.code}: {detail}")
        except Exception as error:  # noqa: BLE001 - retried below
            last = error
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    raise last  # type: ignore[misc]


def discrete(answer: Dict[str, Any], kind: str, multi_picks: int) -> Tuple[str, Dict[str, float]]:
    """The single value written to answers_wide.csv, plus the distribution behind it.

    Jev indexes a ScoreQuestion's criteria from 0, so its "0" is the first anchor. The survey, the
    chat runs and the real 600 all use 1-5, so score keys are shifted up by one here. Getting this
    wrong would silently shift every likert item down a point and make the distributions look far
    more negative than they are.
    """
    raw = answer.get("probabilities") or {}
    if not raw:
        return "", {}
    if answer.get("type") == "score":
        probabilities = {str(int(k) + 1): float(v) for k, v in raw.items()}
    else:
        probabilities = {str(k): float(v) for k, v in raw.items()}
    ranked = sorted(probabilities, key=lambda k: probabilities[k], reverse=True)
    if kind == "multi_choice":
        return "|".join(ranked[:multi_picks]), probabilities
    return ranked[0], probabilities


def git_info() -> Dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.check_output(args, cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:  # noqa: BLE001 - provenance is best-effort
            return ""
    return {
        "path": "research/neo_persona_set/phase3/jev_survey.py",
        "git_commit": run("git", "rev-parse", "HEAD"),
        "git_branch": run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(run("git", "status", "--porcelain")),
        "python": ".".join(str(v) for v in sys.version_info[:3]),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--survey", type=Path, default=chat_runner.DEFAULT_SURVEY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-tag", default="s1-jev-full")
    parser.add_argument("--repeats", type=int, default=1,
                        help="Jev is deterministic given a state, so more than one repeat only "
                             "measures the service's own variability")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--multi-picks", type=int, default=2, help="options kept for Q20")
    parser.add_argument("--drop-census-fields", default="")
    parser.add_argument("--drop-story-fields", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    chat_runner.assert_not_real_data(args.personas, "--personas")
    chat_runner.assert_not_real_data(args.out_dir, "--out-dir")

    drop_census = {f.strip() for f in args.drop_census_fields.split(",") if f.strip()}
    drop_story = {f.strip() for f in args.drop_story_fields.split(",") if f.strip()}

    survey = chat_runner.load_survey(args.survey)
    questions = list(survey.questions)
    kinds = {q.model_dump()["id"]: q.model_dump().get("question_type") for q in questions}
    jev_questions = build_questions(questions)
    preambles: List[str] = []
    for question in questions:
        preamble = question.model_dump().get("preamble")
        if preamble and preamble not in preambles:
            preambles.append(preamble)

    with args.personas.open(encoding="utf-8-sig") as handle:
        personas = list(csv.DictReader(handle))
    if args.limit:
        personas = personas[: args.limit]

    skipped = sorted(set(kinds) - set(jev_questions))
    print(f"{len(personas)} personas x {len(jev_questions)} of {len(kinds)} questions "
          f"({sum(1 for k in jev_questions.values() if k['type'] == 'score')} score, "
          f"{sum(1 for k in jev_questions.values() if k['type'] == 'choice')} choice)")
    if skipped:
        print(f"  not asked (no option list to classify over): {', '.join(skipped)}")
    if drop_census or drop_story:
        print(f"  dropping census={sorted(drop_census)} story={sorted(drop_story)}")
    if args.dry_run:
        sample = build_state(personas[0], preambles, drop_census, drop_story)
        print(json.dumps({"state": sample, "questions": jev_questions}, indent=1)[:2500])
        return 0

    key = load_key()
    started_at = datetime.now(timezone.utc)
    run_id = f"{started_at.strftime('%Y%m%dT%H%M%SZ')}_jev-latest_r1_{args.run_tag}"
    out_dir = args.out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Tuple[int, Dict[str, Any]]] = []
    failures: List[Tuple[str, str]] = []
    raw_path = out_dir / "raw_responses.jsonl"
    clock = time.time()

    def work(item: Tuple[int, Dict[str, str]]) -> Tuple[int, Dict[str, str], Optional[Dict[str, Any]], Optional[str]]:
        index, persona = item
        state = build_state(persona, preambles, drop_census, drop_story)
        try:
            return index, persona, ask(key, {"model": MODEL, "state": state, "questions": jev_questions}, args.timeout), None
        except Exception as error:  # noqa: BLE001 - reported per persona
            return index, persona, None, f"{type(error).__name__}: {error}"

    with raw_path.open("w", encoding="utf-8") as raw_handle, \
            ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for done, (index, persona, response, error) in enumerate(
                pool.map(work, list(enumerate(personas))), start=1):
            if error:
                failures.append((persona["persona_id"], error))
            else:
                raw_handle.write(json.dumps({"persona_id": persona["persona_id"], "response": response}) + "\n")
                rows.append((index, {"persona": persona, "answers": response.get("answers") or {}}))
            if done % 20 == 0 or done == len(personas):
                print(f"  [{done}/{len(personas)}] ok={len(rows)} failed={len(failures)} "
                      f"elapsed={time.time() - clock:.0f}s")

    rows.sort(key=lambda r: r[0])
    question_ids = [q.model_dump()["id"] for q in questions]

    wide_path, long_path, prob_path = (out_dir / n for n in
                                       ("answers_wide.csv", "answers_long.csv", "probabilities.csv"))
    with wide_path.open("w", newline="", encoding="utf-8-sig") as wide_handle, \
            long_path.open("w", newline="", encoding="utf-8-sig") as long_handle, \
            prob_path.open("w", newline="", encoding="utf-8-sig") as prob_handle:
        wide = csv.writer(wide_handle)
        wide.writerow(["run_id", "model", "repeat", "seed", "persona_id", "respondent_id", "trait"] + question_ids)
        long = csv.writer(long_handle)
        long.writerow(["run_id", "model", "repeat", "seed", "persona_id", "respondent_id",
                       "question_id", "question_type", "answer", "answer_json", "is_fallback", "reason"])
        prob = csv.writer(prob_handle)
        prob.writerow(["run_id", "persona_id", "question_id", "option", "probability", "confidence"])

        for position, (_, record) in enumerate(rows, start=1):
            persona, answers = record["persona"], record["answers"]
            respondent_id = f"RESP_{position:03d}"
            wide_row = [run_id, MODEL, 1, "", persona["persona_id"], respondent_id, ""]
            for question_id in question_ids:
                answer = answers.get(question_id) or {}
                value, probabilities = discrete(answer, kinds.get(question_id, ""), args.multi_picks)
                wide_row.append(value)
                long.writerow([run_id, MODEL, 1, "", persona["persona_id"], respondent_id, question_id,
                               kinds.get(question_id, ""), value, json.dumps(value),
                               "true" if not value else "false", ""])
                for option, share in probabilities.items():
                    prob.writerow([run_id, persona["persona_id"], question_id, option,
                                   round(share, 6), answer.get("confidence", "")])
            wide.writerow(wide_row)

    with (out_dir / "questions.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["question_id", "question_type", "asked_as", "options"])
        for question in questions:
            data = question.model_dump()
            asked = (jev_questions.get(data["id"]) or {}).get("type", "not asked")
            writer.writerow([data["id"], data.get("question_type"), asked, "|".join(data.get("options") or [])])

    finished_at = datetime.now(timezone.utc)
    manifest = {
        "run_id": run_id,
        "status": "completed" if not failures else "completed_with_failures",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_sec": round((finished_at - started_at).total_seconds(), 1),
        "script": git_info(),
        "model": {"requested": MODEL, "endpoint": ENDPOINT, "architecture": "classifier, not a chat model"},
        "panel": {
            "personas_file": str(args.personas),
            "personas_sha256": chat_runner.sha256_of_file(args.personas),
            "n_personas": len(personas),
            "n_answered": len(rows),
        },
        "survey": {"file": str(args.survey), "n_questions": len(question_ids),
                   "n_asked": len(jev_questions), "not_asked": skipped},
        "ablation": {"drop_census_fields": sorted(drop_census), "drop_story_fields": sorted(drop_story)},
        "multi_picks": args.multi_picks,
        "failures": [{"persona_id": p, "error": e} for p, e in failures],
        "notes": (
            "Each question is answered in isolation, so there is no within-respondent leakage to "
            "control for. answers_wide.csv holds the argmax so the run is comparable to a chat run; "
            "probabilities.csv holds the full distribution."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # A short human-readable summary, as the chat runner writes, so a run folder can be read
    # without loading anything.
    likert = [q.model_dump()["id"] for q in questions if q.model_dump().get("question_type") == "likert"]
    levels: Dict[str, int] = {}
    for _, record in rows:
        for question_id in likert:
            value, _ = discrete(record["answers"].get(question_id) or {}, "likert", args.multi_picks)
            if value:
                levels[value] = levels.get(value, 0) + 1
    total = sum(levels.values()) or 1
    summary = [
        f"# {run_id}",
        "",
        f"- personas: {len(rows)} of {len(personas)}, failures {len(failures)}",
        f"- questions asked: {len(jev_questions)} of {len(question_ids)}"
        + (f" (not asked: {', '.join(skipped)})" if skipped else ""),
        f"- duration: {manifest['duration_sec']}s",
        f"- ablation: census={sorted(drop_census) or 'none'} story={sorted(drop_story) or 'none'}",
        "",
        "## Likert answer mix (argmax over each question's distribution)",
        "",
        "| level | share |",
        "| --- | --- |",
    ]
    summary += [f"| {level} | {levels.get(level, 0) / total:.3f} |" for level in ("1", "2", "3", "4", "5")]
    summary += [
        "",
        "answers_wide.csv holds the argmax so this run is comparable to a chat run.",
        "probabilities.csv holds the full distribution behind every answer.",
    ]
    (out_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"\n--- {run_id}: {'COMPLETED' if not failures else 'COMPLETED WITH FAILURES'} | "
          f"respondents={len(rows)} answers={len(rows) * len(jev_questions)} "
          f"failed={len(failures)} in {manifest['duration_sec']}s -> {out_dir}")
    for persona_id, error in failures[:5]:
        print(f"    FAILED {persona_id}: {error}")
    return 0 if len(rows) == len(personas) else 1


if __name__ == "__main__":
    raise SystemExit(main())
