"""Two chat models answer with reasons; Jev then decides between them.

R004 tried this with GLM-5 as the judge and concluded the judge "does not move the distribution
because it judges plausibility with the same affordability lens". Jev is a different kind of judge:
it is a classifier, it sees each comparison in isolation, and it returns a probability over the two
candidates rather than a verdict. So the question is whether a judge that does not generate prose
weighs the two reasons differently.

Stage 1  DeepSeek and Qwen each answer Q1, Q2 and Q6 for every persona and give a reason per answer.
Stage 2  For each persona and question, Jev reads the persona, the question, and both
         (answer, reason) pairs, and returns P(A) / P(B).

The judged distribution is then built two ways, and they are reported separately because they mean
different things:

  hard   take the candidate Jev gives the higher probability, and use its answer
  soft   weight each candidate's answer by Jev's probability, so a 55/45 judgement contributes
         both answers in that ratio rather than discarding the loser

Candidate order is randomised per item and recorded, so a judge that simply prefers whichever
option is shown first would show up as a position bias rather than hiding inside the result.

Usage:
    python research/neo_persona_set/phase3/jev_judge.py --limit 100
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from jev_pilot import (  # noqa: E402
    API_ENV, CENSUS_FIELDS, DEFAULT_PERSONAS, ENDPOINT, MODEL, PRODUCT, QUESTIONS,
    STORY_FIELDS, build_state, spearman,
)

REPO_ROOT = HERE.parents[2]
DEFAULT_OUT = HERE.parent / "out" / "jev_runs"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CHAT_MODELS = ["deepseek/deepseek-v4-pro-0813", "qwen/qwen3.7-plus"]

LIKERT = {
    "Q1_purchase_interest": QUESTIONS["Q1_purchase_interest"]["criteria"],
    "Q2_purchase_likelihood": QUESTIONS["Q2_purchase_likelihood"]["criteria"],
}
CHOICES = list(QUESTIONS["Q6_greatest_barrier"]["criteria"])


def load_key(name: str) -> str:
    key = os.getenv(name, "").strip()
    if not key and API_ENV.exists():
        for line in API_ENV.read_text().splitlines():
            if line.startswith(f"{name}="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit(f"{name} not set in {API_ENV}")
    return key


def persona_block(persona: dict) -> str:
    lines = []
    for field in CENSUS_FIELDS:
        value = persona.get(field)
        if value not in (None, ""):
            lines.append(f"- {field}: {value}")
    for field in STORY_FIELDS:
        value = persona.get(field)
        if value not in (None, ""):
            lines.append(f"- {field.removeprefix('story_')}: {value}")
    return "\n".join(lines)


CHAT_SYSTEM = (
    "You are answering a consumer survey AS the person described. Answer exactly as they would, "
    "using their circumstances. Give a one-sentence reason for each answer naming the specific "
    "thing about this person that drove it.\n\n"
    "Return ONLY JSON:\n"
    '{"Q1":{"answer":<1-5>,"reason":"..."},'
    '"Q2":{"answer":<1-5>,"reason":"..."},'
    '"Q6":{"answer":"<one option verbatim>","reason":"..."}}'
)


def chat_prompt(persona: dict) -> str:
    q1 = " / ".join(f"{i+1}={c}" for i, c in enumerate(LIKERT["Q1_purchase_interest"]))
    q2 = " / ".join(f"{i+1}={c}" for i, c in enumerate(LIKERT["Q2_purchase_likelihood"]))
    options = "\n".join(f"  - {c}" for c in CHOICES)
    return (
        f"PRODUCT\n{PRODUCT}\n\nTHE PERSON\n{persona_block(persona)}\n\n"
        f"Q1. Based on the product description, how interested would you be in purchasing and "
        f"installing a Tahoe Mini at approximately $23,000?\n   {q1}\n\n"
        f"Q2. How likely are you to purchase a Tahoe Mini within the next 24 months?\n   {q2}\n\n"
        f"Q6. Which one barrier would be the single greatest obstacle preventing you from "
        f"purchasing?\n{options}\n"
    )


def post(url: str, body: dict, headers: dict, timeout: int, retries: int = 4) -> dict:
    payload = json.dumps(body).encode()
    last: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = error.read().decode()[:160]
            if error.code not in (408, 429) and error.code < 500:
                raise RuntimeError(f"HTTP {error.code}: {detail}") from error
            last = RuntimeError(f"HTTP {error.code}: {detail}")
        except Exception as error:  # noqa: BLE001 - retried below
            last = error
        if attempt < retries - 1:
            time.sleep(2 ** attempt + random.random())
    raise last  # type: ignore[misc]


def parse_json_block(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON in: {text[:160]}")
    return json.loads(cleaned[start : end + 1])


def ask_chat(key: str, model: str, persona: dict, temperature: float, timeout: int) -> dict:
    body = {
        "model": model,
        "temperature": temperature,
        "max_tokens": 900,
        # Reasoning must be OFF, matching run_survey.py. With it on, both models put their
        # output in the reasoning field and return content=None, and Minh found they also
        # burn ~3k tokens per persona and truncate the answer.
        "reasoning": {"enabled": False},
        "messages": [
            {"role": "system", "content": CHAT_SYSTEM},
            {"role": "user", "content": chat_prompt(persona)},
        ],
    }
    out = post(OPENROUTER_URL, body,
               {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout)
    message = out["choices"][0]["message"]
    content = message.get("content")
    if not content:
        raise RuntimeError(
            f"empty content (finish_reason={out['choices'][0].get('finish_reason')}, "
            f"keys={sorted(message)})"
        )
    return parse_json_block(content)


def ask_jev_judge(key: str, persona: dict, items: list[dict], timeout: int) -> dict:
    """One Jev call per persona carrying every judgement for that persona.

    Each question becomes its own named choice question, so they are still judged in isolation —
    the batching is only to save round trips.
    """
    state = build_state(persona, set(), set())
    questions = {}
    for item in items:
        questions[item["key"]] = {
            "type": "choice",
            "instructions": (
                f"Survey question: {item['question']}\n"
                f"Two analysts each predicted how THIS person would answer, with their reasoning.\n"
                f"Option A answered \"{item['a_answer']}\" because: {item['a_reason']}\n"
                f"Option B answered \"{item['b_answer']}\" because: {item['b_reason']}\n"
                f"Which prediction better reflects how this particular person would actually answer?"
            ),
            "criteria": {
                "A": "Option A's answer and reasoning fit this person better",
                "B": "Option B's answer and reasoning fit this person better",
            },
        }
    body = {"model": MODEL, "state": state, "questions": questions}
    return post(ENDPOINT, body,
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout)


def likert(value) -> int | None:
    try:
        number = int(str(value).strip()[0])
    except (ValueError, IndexError):
        return None
    return number if 1 <= number <= 5 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--tag", default="jevjudge")
    args = parser.parse_args()

    with args.personas.open(encoding="utf-8-sig") as handle:
        personas = list(csv.DictReader(handle))
    if args.limit:
        personas = personas[: args.limit]

    or_key, ts_key = load_key("OPENROUTER_API_KEY"), load_key("TYPESAFE_API_KEY")
    rng = random.Random(args.seed)
    print(f"{len(personas)} personas | chat: {', '.join(CHAT_MODELS)} | judge: {MODEL}\n")

    # ---- Stage 1: both chat models answer with reasons ----
    answers: dict[str, dict[str, dict]] = {p["persona_id"]: {} for p in personas}
    failures: list[str] = []

    def chat_work(args_tuple):
        persona, model = args_tuple
        try:
            return persona["persona_id"], model, ask_chat(or_key, model, persona,
                                                          args.temperature, args.timeout), None
        except Exception as error:  # noqa: BLE001
            return persona["persona_id"], model, None, f"{type(error).__name__}: {error}"

    jobs = [(p, m) for p in personas for m in CHAT_MODELS]
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(chat_work, j) for j in jobs]
        for done, future in enumerate(as_completed(futures), start=1):
            pid, model, payload, error = future.result()
            if error:
                failures.append(f"{pid}/{model.split('/')[0]}: {error[:80]}")
            else:
                answers[pid][model] = payload
            if done % 40 == 0 or done == len(jobs):
                print(f"  stage 1: {done}/{len(jobs)}")
    print(f"  stage 1 done in {time.time()-started:.0f}s, {len(failures)} failures")

    usable = [p for p in personas if len(answers[p["persona_id"]]) == len(CHAT_MODELS)]
    print(f"  {len(usable)} personas have both models' answers\n")

    # ---- Stage 2: Jev judges between the two reasons ----
    deepseek, qwen = CHAT_MODELS
    judged: list[dict] = []

    def judge_work(persona):
        pid = persona["persona_id"]
        a_model, b_model = (deepseek, qwen) if rng.random() < 0.5 else (qwen, deepseek)
        items = []
        for key, qid in [("Q1_purchase_interest", "Q1"), ("Q2_purchase_likelihood", "Q2"),
                         ("Q6_greatest_barrier", "Q6")]:
            a, b = answers[pid][a_model].get(qid, {}), answers[pid][b_model].get(qid, {})
            if not a.get("reason") or not b.get("reason"):
                continue
            items.append({
                "key": key, "question": QUESTIONS[key]["instructions"],
                "a_answer": a.get("answer"), "a_reason": a.get("reason"),
                "b_answer": b.get("answer"), "b_reason": b.get("reason"),
            })
        if not items:
            return pid, None, None, None, "no reasons"
        try:
            return pid, a_model, b_model, ask_jev_judge(ts_key, persona, items, args.timeout), None
        except Exception as error:  # noqa: BLE001
            return pid, a_model, b_model, None, f"{type(error).__name__}: {error}"

    started = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(judge_work, p) for p in usable]
        for done, future in enumerate(as_completed(futures), start=1):
            pid, a_model, b_model, payload, error = future.result()
            if error or not payload:
                failures.append(f"{pid}/judge: {error}")
                continue
            persona = next(p for p in usable if p["persona_id"] == pid)
            row = {"persona_id": pid, "income": float(persona["exact_household_income"]),
                   "a_model": a_model, "b_model": b_model}
            for key in ("Q1_purchase_interest", "Q2_purchase_likelihood", "Q6_greatest_barrier"):
                verdict = payload["answers"].get(key)
                if not verdict:
                    continue
                probabilities = verdict["probabilities"]
                row[f"{key}_pA"] = probabilities.get("A", 0.0)
                row[f"{key}_pick"] = verdict["choice"]
            judged.append(row)
            if done % 25 == 0 or done == len(usable):
                print(f"  stage 2: {done}/{len(usable)}")
    print(f"  stage 2 done in {time.time()-started:.0f}s\n")

    if not judged:
        raise SystemExit("no judged rows")

    # ---- Build distributions ----
    def arm_shares(model: str) -> list[float]:
        counts = [0] * 5
        for row in judged:
            value = likert(answers[row["persona_id"]][model].get("Q1", {}).get("answer"))
            if value:
                counts[value - 1] += 1
        total = sum(counts) or 1
        return [c / total for c in counts]

    hard, soft = [0.0] * 5, [0.0] * 5
    hard_scores, soft_scores, incomes = [], [], []
    position_a_wins = 0
    for row in judged:
        pa = row.get("Q1_purchase_interest_pA")
        if pa is None:
            continue
        a_value = likert(answers[row["persona_id"]][row["a_model"]].get("Q1", {}).get("answer"))
        b_value = likert(answers[row["persona_id"]][row["b_model"]].get("Q1", {}).get("answer"))
        if not a_value or not b_value:
            continue
        if pa >= 0.5:
            position_a_wins += 1
        winner = a_value if pa >= 0.5 else b_value
        hard[winner - 1] += 1
        soft[a_value - 1] += pa
        soft[b_value - 1] += 1 - pa
        hard_scores.append(winner)
        soft_scores.append(a_value * pa + b_value * (1 - pa))
        incomes.append(row["income"])

    hard = [c / max(sum(hard), 1) for c in hard]
    soft = [c / max(sum(soft), 1) for c in soft]

    ds_shares, qw_shares = arm_shares(deepseek), arm_shares(qwen)
    ds_scores = [likert(answers[r["persona_id"]][deepseek].get("Q1", {}).get("answer")) for r in judged]
    qw_scores = [likert(answers[r["persona_id"]][qwen].get("Q1", {}).get("answer")) for r in judged]
    inc_all = [r["income"] for r in judged]
    pairs_ds = [(i, s) for i, s in zip(inc_all, ds_scores) if s]
    pairs_qw = [(i, s) for i, s in zip(inc_all, qw_scores) if s]

    summary = {
        "run": f"{time.strftime('%Y%m%dT%H%MZ', time.gmtime())}_{args.tag}",
        "personas_judged": len(judged),
        "chat_models": CHAT_MODELS,
        "judge": MODEL,
        "failures": len(failures),
        "q1_shares": {
            "deepseek": [round(x, 4) for x in ds_shares],
            "qwen": [round(x, 4) for x in qw_shares],
            "jev_judged_hard": [round(x, 4) for x in hard],
            "jev_judged_soft": [round(x, 4) for x in soft],
            "real": [0.38, 0.20, 0.18, 0.16, 0.07],
        },
        "rho_income_q1": {
            "deepseek": round(spearman([p[0] for p in pairs_ds], [p[1] for p in pairs_ds]), 4),
            "qwen": round(spearman([p[0] for p in pairs_qw], [p[1] for p in pairs_qw]), 4),
            "jev_judged_hard": round(spearman(incomes, hard_scores), 4),
            "jev_judged_soft": round(spearman(incomes, soft_scores), 4),
            "real": 0.10,
        },
        "judge_position_bias_share_A": round(position_a_wins / max(len(hard_scores), 1), 4),
        "elapsed_note": "stage1 chat + stage2 jev",
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_dir = args.out_dir / summary["run"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (run_dir / "judged.json").write_text(json.dumps(
        {"judged": judged, "answers": answers}, indent=2, default=str) + "\n")
    if failures:
        (run_dir / "failures.txt").write_text("\n".join(failures) + "\n")

    print(f"{'arm':<22}{'1':>7}{'2':>7}{'3':>7}{'4':>7}{'5':>7}{'rho':>9}")
    print("-" * 66)
    for label, shares, key in [
        ("DeepSeek", ds_shares, "deepseek"), ("Qwen", qw_shares, "qwen"),
        ("Jev-judged (hard)", hard, "jev_judged_hard"), ("Jev-judged (soft)", soft, "jev_judged_soft"),
    ]:
        print(f"  {label:<20}" + "".join(f"{s:>7.2f}" for s in shares)
              + f"{summary['rho_income_q1'][key]:>9.3f}")
    print(f"  {'REAL 600':<20}" + "".join(f"{s:>7.2f}" for s in [0.38, 0.20, 0.18, 0.16, 0.07])
          + f"{0.10:>9.3f}")
    print(f"\n  judge picked position A {summary['judge_position_bias_share_A']:.0%} "
          f"(0.50 = no position bias)")
    print(f"Wrote {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
