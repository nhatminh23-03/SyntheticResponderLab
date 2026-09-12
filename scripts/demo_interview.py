#!/usr/bin/env python3
"""Open one real persona record and interview it — the Sept 3 demo.

    python3 scripts/demo_interview.py --csv <personas.csv>
    python3 scripts/demo_interview.py --csv <personas.csv> --persona P007 \
        --question "What would stop you from buying one?"

Prints the persona, the exact system prompt the interview flow builds from it, and the
persona's live answer. Without OPENROUTER_API_KEY it still shows persona + prompt and says
so plainly, so the handoff format is demonstrable with or without a key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps/api/src"))

from simulation.persona_csv import load_persona, load_personas  # noqa: E402
from simulation.interview_prompt_builder import build_system_prompt  # noqa: E402

DEFAULT_QUESTION = (
    "Neo Smart Living makes the Tahoe Mini, a 117-square-foot factory-built studio "
    "that installs in a backyard, priced around $23,000. What is your first reaction, "
    "and what would you use it for, if anything?"
)

# Written from the public product concept only. Nothing from the 600 real survey answers
# may appear here — that contamination rule is Ann's, and it is what makes the September
# comparison mean anything.
PRODUCT = {
    "product_name": "Tahoe Mini by Neo Smart Living",
    "product_description": (
        "A compact 117-square-foot factory-built studio that is delivered and installed in a "
        "backyard. It is not an ADU and has no kitchen or bathroom."
    ),
    "price_range": "about $23,000",
    "target_customer": "homeowners with usable outdoor space",
    "key_features": ["factory-built", "installs in a backyard", "117 square feet"],
}


def ask_openrouter(system_prompt: str, question: str, model: str) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        env_file = REPO_ROOT / "apps/api/.env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        return ""

    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                "temperature": 0.8,
                "max_tokens": 900,
            }
        ).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)
    return payload["choices"][0]["message"]["content"].strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Persona CSV from the Census pipeline.")
    parser.add_argument("--persona", default=None, help="persona_id; default is the first row.")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--list", action="store_true", help="List the personas and exit.")
    parser.add_argument("--json", action="store_true", help="Keep the batch runner's JSON output contract.")
    args = parser.parse_args()

    if args.list:
        for persona in load_personas(args.csv):
            profile = persona["census_profile"].split(".")[0] or "(no census detail)"
            print(f"  {persona['persona_id']:<8} {profile}")
        return 0

    persona = load_persona(args.csv, args.persona)

    print("=" * 78)
    print(f"PERSONA {persona['persona_id']}  (loaded from {Path(args.csv).name})")
    print("=" * 78)
    print(persona["census_profile"])
    print(f"\nlifestyle: {', '.join(persona['lifestyle_tags']) or '(none)'}")
    print(f"buckets:   age={persona['age_bucket']}  income={persona['income_bucket']}  "
          f"tenure={persona['ownership']}  home={persona['home_type']}")
    print(f"fit_tier:  {persona['fit_tier'] or '(blank — retired, scored after the interview)'}")

    system_prompt = build_system_prompt(persona, PRODUCT, None)
    if not args.json:
        # The shared builder ends with a "return only JSON" instruction meant for the batch
        # runner. A single spoken question should come back as speech, not a JSON blob.
        system_prompt = "\n".join(
            line for line in system_prompt.splitlines()
            if "JSON" not in line
        ).rstrip() + "\n- Answer this one question conversationally, in plain prose."
    print("\n" + "=" * 78)
    print("SYSTEM PROMPT BUILT FROM THAT RECORD")
    print("=" * 78)
    print(system_prompt)

    print("\n" + "=" * 78)
    print("INTERVIEWER")
    print("=" * 78)
    print(args.question)

    print("\n" + "=" * 78)
    print(f"{persona['persona_id']} ANSWERS  (model: {args.model})")
    print("=" * 78)
    try:
        answer = ask_openrouter(system_prompt, args.question, args.model)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as exc:
        print(f"[model call failed: {exc}]")
        return 1

    if not answer:
        print("[no OPENROUTER_API_KEY set — persona and prompt above are real; add the key")
        print(" to apps/api/.env and re-run to get the live answer]")
        return 0

    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
