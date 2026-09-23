"""Pilot: run personas through TypeSafe's Jev classifier and measure the income gradient.

Jev is not a chat model. One request carries a `state` (the persona plus the product stimulus) and
a named map of questions; each question is answered in isolation and comes back as a probability
distribution over the options, not a single pick. Two consequences for this project:

  * A stance formed on Q1 cannot leak into Q2, because the questions never share a generation.
    R007 found that leakage is real for chat models; here it is absent by construction.
  * Every persona yields a distribution, so the population estimate is the average of the
    probability vectors rather than a histogram of argmax picks.

The pilot exists to answer one question cheaply before anyone builds a full adapter:

    Is rho(income, E[Q1]) near the real 0.10, or near the 0.67-0.72 that DeepSeek and Qwen show?

Income is read from the persona file for the correlation but the exact figure is still sent to the
model here, exactly as the baseline sends it. This is the baseline condition for Jev, not an
ablation.

Usage:
    python research/neo_persona_set/phase3/jev_pilot.py --limit 20
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
API_ENV = REPO_ROOT / "apps/api/.env"
DEFAULT_PERSONAS = HERE.parent / "out" / "phase1_interview_matched600_s1.csv"
DEFAULT_OUT = HERE.parent / "out" / "jev_runs"

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

# The product stimulus, matching what the chat runner sends before Q1.
PRODUCT = (
    "The Tahoe Mini by Neo Smart Living is a compact 117-square-foot factory-built backyard unit — "
    "a private standalone studio, workspace, or guest room, about 9ft x 13ft. It is delivered as "
    "flat-packed panels and installed in most backyards in about one day. The approximate price is "
    "$23,000 including sales tax, delivery, installation, and warranty. Wall panels are modular and "
    "configurable. It is NOT an ADU: no plumbing, no kitchen, classified as a non-habitable "
    "accessory structure. At 117 sq ft it sits under California's ~120 sq ft threshold, so it often "
    "does not require a building permit, though local ordinances and HOA rules still apply. Standard "
    "features include pre-wired electrical, a smart entry lock, dual-pane floor-to-ceiling glass, and "
    "a pitched roof."
)

# Wording copied from the survey file so the pilot is comparable to the chat runs.
QUESTIONS = {
    "Q1_purchase_interest": {
        "type": "score",
        "instructions": (
            "Based on the product description, how interested would this person be in purchasing "
            "and installing a Tahoe Mini at the approximately $23,000 delivered-and-installed price "
            "point?"
        ),
        "criteria": [
            "Not at all interested",
            "Slightly interested",
            "Moderately interested",
            "Very interested",
            "Extremely interested",
        ],
    },
    "Q2_purchase_likelihood": {
        "type": "score",
        "instructions": (
            "How likely is this person to purchase a Tahoe Mini within the next 24 months?"
        ),
        "criteria": [
            "Definitely would not",
            "Probably would not",
            "Might or might not",
            "Probably would",
            "Definitely would",
        ],
    },
    "Q6_greatest_barrier": {
        "type": "choice",
        "instructions": (
            "Which one barrier would be the single greatest obstacle preventing this person from "
            "purchasing a Tahoe Mini?"
        ),
        "criteria": {
            "The total cost (~$23,000)": "Price is the single biggest obstacle",
            "HOA restrictions or community rules": "Community rules would block or complicate it",
            "Uncertainty about whether a building permit is required": "Permitting uncertainty",
            "Limited backyard space or access": "Not enough usable space or access to install",
            "Lack of financing options": "Could manage it only with financing that is unavailable",
        },
    },
}

# Persona fields sent as the state. Kept close to what the chat runner sends so the two are
# comparable; the ablations will later drop subsets of these by name.
CENSUS_FIELDS = [
    "exact_age", "sex", "region", "state", "exact_household_income", "income_bucket",
    "household_size", "children_in_household", "household_type", "marital_status", "education",
    "occupation", "employment_status", "work_mode", "home_type", "tenure_detail", "bedrooms",
    "rooms", "year_built", "moved_in", "vehicles", "housing_cost_pct_of_income",
]
STORY_FIELDS = [
    "story_headline", "story_biography", "story_daily_routine", "story_weekend_routine",
    "story_household_and_home", "story_outdoor_space", "story_home_projects", "story_work_setup",
    "story_space_pressure", "story_money_decisions", "story_priorities", "story_financial_picture",
    "story_free_time", "story_communication_style",
]


def load_key() -> str:
    key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not key and API_ENV.exists():
        for line in API_ENV.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit(f"TYPESAFE_API_KEY not set. Add it to {API_ENV}")
    return key


def build_state(persona: dict, drop_census: set[str], drop_story: set[str]) -> dict:
    """Assemble the state Jev reads. Dropping fields here is how the ablations will work."""
    state: dict = {"product": PRODUCT, "respondent": {}}
    for field in CENSUS_FIELDS:
        if field in drop_census:
            continue
        value = persona.get(field)
        if value not in (None, ""):
            state["respondent"][field] = value
    for field in STORY_FIELDS:
        if field in drop_story:
            continue
        value = persona.get(field)
        if value not in (None, ""):
            state["respondent"][field.removeprefix("story_")] = value
    return state


def ask(key: str, state: dict, timeout: int, retries: int = 4) -> dict:
    body = json.dumps({"model": MODEL, "state": state, "questions": QUESTIONS}).encode()
    last: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            ENDPOINT, data=body, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = error.read().decode()[:200]
            # 4xx other than rate limiting will not fix themselves; fail fast rather than retry.
            if error.code not in (408, 429) and error.code < 500:
                raise RuntimeError(f"HTTP {error.code}: {detail}") from error
            last = RuntimeError(f"HTTP {error.code}: {detail}")
        except Exception as error:  # noqa: BLE001 - retried below
            last = error
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    raise last  # type: ignore[misc]


def expected_score(answer: dict) -> float:
    """Jev returns `score` already probability-weighted; recompute as a check on the contract."""
    probabilities = answer.get("probabilities") or {}
    return sum(int(level) * share for level, share in probabilities.items())


def spearman(xs: list[float], ys: list[float]) -> float:
    """Rank correlation, average ranks for ties. Hand-rolled to match phase3/metrics.py."""
    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
                stop += 1
            average = (index + stop) / 2 + 1
            for position in range(index, stop + 1):
                out[order[position]] = average
            index = stop + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--tag", default="pilot")
    parser.add_argument("--drop-census-fields", default="", help="comma-separated, for ablations")
    parser.add_argument("--drop-story-fields", default="", help="comma-separated, for ablations")
    args = parser.parse_args()

    drop_census = {f.strip() for f in args.drop_census_fields.split(",") if f.strip()}
    drop_story = {f.strip() for f in args.drop_story_fields.split(",") if f.strip()}

    with args.personas.open(encoding="utf-8-sig") as handle:
        personas = list(csv.DictReader(handle))
    if args.limit:
        personas = personas[: args.limit]
    print(f"{len(personas)} personas from {args.personas.name}")
    if drop_census or drop_story:
        print(f"  dropping census={sorted(drop_census)} story={sorted(drop_story)}")

    key = load_key()
    results: list[dict] = []
    failures: list[tuple[str, str]] = []

    def work(persona: dict) -> tuple[dict, dict | None, str | None]:
        try:
            state = build_state(persona, drop_census, drop_story)
            return persona, ask(key, state, args.timeout), None
        except Exception as error:  # noqa: BLE001 - reported per persona
            return persona, None, f"{type(error).__name__}: {error}"

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(work, p) for p in personas]
        for done, future in enumerate(as_completed(futures), start=1):
            persona, payload, error = future.result()
            if error:
                failures.append((persona["persona_id"], error))
                continue
            answers = payload["answers"]
            q1, q2 = answers["Q1_purchase_interest"], answers["Q2_purchase_likelihood"]
            q6 = answers["Q6_greatest_barrier"]
            results.append({
                "persona_id": persona["persona_id"],
                "income": float(persona["exact_household_income"]),
                "income_bucket": persona["income_bucket"],
                "age": int(persona["exact_age"]),
                "q1_score": q1["score"],
                "q1_check": round(expected_score(q1), 4),
                "q1_confidence": q1["confidence"],
                "q1_probs": q1["probabilities"],
                "q2_score": q2["score"],
                "q2_confidence": q2["confidence"],
                "q6_choice": q6["choice"],
                "q6_cost_prob": q6["probabilities"].get("The total cost (~$23,000)", 0.0),
                "input_tokens": payload["usage"]["input_tokens"],
                "output_tokens": payload["usage"]["output_tokens"],
            })
            if done % 5 == 0 or done == len(personas):
                print(f"  {done}/{len(personas)}")

    if failures:
        print(f"\n{len(failures)} failed:")
        for persona_id, error in failures[:5]:
            print(f"  {persona_id}  {error[:110]}")
    if not results:
        raise SystemExit("no usable answers")

    results.sort(key=lambda r: r["persona_id"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%MZ", time.gmtime())
    run_dir = args.out_dir / f"{stamp}_{args.tag}"
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "answers.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "persona_id", "income", "income_bucket", "age", "q1_score", "q1_confidence",
            "q1_p1", "q1_p2", "q1_p3", "q1_p4", "q1_p5", "q2_score", "q2_confidence",
            "q6_choice", "q6_cost_prob",
        ])
        for r in results:
            p = r["q1_probs"]
            writer.writerow([
                r["persona_id"], r["income"], r["income_bucket"], r["age"],
                r["q1_score"], r["q1_confidence"],
                p.get("0", 0), p.get("1", 0), p.get("2", 0), p.get("3", 0), p.get("4", 0),
                r["q2_score"], r["q2_confidence"], r["q6_choice"], r["q6_cost_prob"],
            ])

    # Expected shares: average the probability vectors rather than counting argmax picks.
    shares = [statistics.mean(r["q1_probs"].get(str(k), 0.0) for r in results) for k in range(5)]
    rho = spearman([r["income"] for r in results], [r["q1_score"] for r in results])
    rho_q2 = spearman([r["income"] for r in results], [r["q2_score"] for r in results])
    tokens_in = sum(r["input_tokens"] for r in results)

    summary = {
        "run": run_dir.name,
        "model": MODEL,
        "personas": len(results),
        "failed": len(failures),
        "dropped_census_fields": sorted(drop_census),
        "dropped_story_fields": sorted(drop_story),
        "q1_expected_shares": [round(s, 4) for s in shares],
        "q1_top2_share": round(shares[3] + shares[4], 4),
        "q1_mean_score": round(statistics.mean(r["q1_score"] for r in results), 4),
        "q1_score_sd": round(statistics.pstdev([r["q1_score"] for r in results]), 4),
        "q1_mean_confidence": round(statistics.mean(r["q1_confidence"] for r in results), 4),
        "rho_income_q1": round(rho, 4),
        "rho_income_q2": round(rho_q2, 4),
        "q1_eq_q2_argmax_share": round(
            sum(1 for r in results if round(r["q1_score"]) == round(r["q2_score"])) / len(results), 4
        ),
        "q6_cost_top_share": round(
            sum(1 for r in results if r["q6_choice"].startswith("The total cost")) / len(results), 4
        ),
        "q6_mean_cost_probability": round(statistics.mean(r["q6_cost_prob"] for r in results), 4),
        "input_tokens": tokens_in,
        "approx_usd": round(tokens_in / 1e6 * 0.042, 6),
        "elapsed_seconds": round(time.time() - started, 1),
        "reference": {
            "real_rho_income_q1": 0.10,
            "deepseek_rho": 0.67,
            "qwen_rho": 0.72,
            "real_q1_shares": [0.38, 0.20, 0.18, 0.16, 0.07],
        },
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (run_dir / "raw_questions.json").write_text(json.dumps(QUESTIONS, indent=2) + "\n")

    print(f"\n{'':22}{'1':>7}{'2':>7}{'3':>7}{'4':>7}{'5':>7}")
    print(f"  {'Jev expected shares':<20}" + "".join(f"{s:>7.2f}" for s in shares))
    print(f"  {'real 600':<20}" + "".join(f"{s:>7.2f}" for s in summary['reference']['real_q1_shares']))
    print()
    print(f"  rho(income, E[Q1])    {summary['rho_income_q1']:>6}   "
          f"(real 0.10 | DeepSeek 0.67 | Qwen 0.72)")
    print(f"  rho(income, E[Q2])    {summary['rho_income_q2']:>6}")
    print(f"  top-2 share (4+5)     {summary['q1_top2_share']:>6}   (real 0.23)")
    print(f"  mean confidence       {summary['q1_mean_confidence']:>6}")
    print(f"  Q6 'cost' top choice  {summary['q6_cost_top_share']:>6}   (DeepSeek 0.98 | Qwen 0.87)")
    print(f"  cost ~= ${summary['approx_usd']:.4f}   {summary['elapsed_seconds']}s")
    print(f"\nWrote {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
