"""Phase 1, step 2 — have an OpenRouter model write each persona's story.

Bias controls, in order of how much they actually do:

1. Race and Hispanic origin were never downloaded. The pipeline cannot leak what it does not hold.
2. Names are assigned from a fixed pool by an independent random stream (see names.py), so a name
   cannot correlate with income, occupation, or county. Letting the model choose names produced
   exactly that correlation.
3. The model is told the name was randomly assigned and carries no information, and is forbidden
   from writing ethnicity, heritage, immigration status, religion, or accent.
4. audit_bias.py checks the finished stories for the correlations this is meant to prevent.

The story is a general life profile. It deliberately contains NO reaction to any product: these
personas will later answer a survey, and pre-writing their opinion would bias that answer and make
any comparison against the real respondents circular.

Usage:
    python phase1/write_stories.py [--model google/gemini-2.5-flash] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import names as name_pool  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "out"
CACHE_DIR = OUT_DIR / "phase1_story_cache"
REPO_ROOT = HERE.parents[2]
LLM_CLIENT_PATH = REPO_ROOT / "apps/api/legacy_runtime/backend/simulation/llm_client.py"
API_ENV_PATH = REPO_ROOT / "apps/api/.env"

SYSTEM_PROMPT = """\
You write short, factual profiles of American households for a market-research panel.

You will be given a REAL household's record from US Census microdata. Write a believable person who
fits that record exactly.

ABSOLUTE RULES ON BIAS — these override everything else:
- The person's name was assigned at random from a fixed list. It tells you NOTHING about them.
  Never infer ethnicity, race, heritage, ancestry, immigration status, religion, language, or
  accent from the name, the county, the occupation, or the income.
- Write no ethnic, racial, cultural, religious, or national-origin characterisation of any kind.
  No "first-generation", no "traditional family values", no heritage foods, no bilingual notes,
  no cultural community references.
- Do not use income to imply sophistication, taste, intelligence, work ethic, or family structure.
  A lower-income household is not more chaotic and a higher-income one is not more refined.
- Describe what this person DOES, not what kind of person they supposedly are.

ACCURACY RULES:
- Never contradict the Census record. Household size, children, marital status, occupation,
  education, commute, and home details are facts, not suggestions.
- If the record says the person is not working, do not give them a job.
- Household income is for the WHOLE household and may include several earners. Do not assume the
  named person earns all of it.
- No statistics, no percentages, no market-research jargon.
- Do not mention any product, purchase, or buying intention. This is a life profile only.

Return ONLY valid JSON with exactly these keys:
  "headline"            one neutral phrase under 70 characters describing their situation
  "biography"           3-4 sentences: work, household, how long in the home
  "daily_routine"       2-3 sentences on a typical weekday
  "household_and_home"  2-3 sentences on the house itself and who lives there
  "priorities"          array of 3 short strings — what they are focused on right now
  "financial_picture"   2 sentences on how money works in this household
  "free_time"           2 sentences on what they do outside work
"""


def load_llm_client():
    if not LLM_CLIENT_PATH.exists():
        raise SystemExit(f"LLM client not found at {LLM_CLIENT_PATH}")
    spec = importlib.util.spec_from_file_location("app_llm_client", LLM_CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_prompt(persona: dict) -> str:
    """Render the Census record. Only facts the household actually reported appear here."""
    lines = [
        "CENSUS RECORD (every line is real data about one household):",
        f"- Assigned name: {persona['name']}  (random, carries no information)",
        f"- Age: {persona['age']}",
        f"- Sex: {persona['sex']}",
        f"- County: {persona['county']}, California",
        f"- Marital status: {persona['marital_status']}",
        f"- Education: {persona['education']}",
        f"- Employment status: {persona['employment_status']}",
    ]
    if persona.get("occupation") and persona["occupation"] not in {"None", None}:
        lines.append(f"- Occupation: {persona['occupation']}")
    if persona.get("hours_worked_per_week"):
        lines.append(f"- Usual hours worked per week: {persona['hours_worked_per_week']}")
    if persona.get("commute_mode"):
        commute = persona["commute_mode"]
        if persona.get("commute_minutes"):
            commute += f", about {persona['commute_minutes']} minutes each way"
        lines.append(f"- Commute: {commute}")

    lines += [
        f"- Total household income: ${persona['household_income']:,} per year (all earners combined)",
        f"- Household size: {persona['household_size']} people",
        f"- Children in household: {persona['children_in_household']}",
        f"- Household type: {persona['household_type']}",
        f"- Home: detached single-family house, {persona['bedrooms']} bedrooms, {persona['rooms']} rooms",
        f"- Tenure: {persona['tenure']}",
        f"- Structure built: {persona['year_built']}",
        f"- Moved in: {persona['moved_in']}",
        f"- Vehicles: {persona['vehicles']}",
    ]
    if persona.get("housing_cost_pct_of_income") is not None:
        lines.append(
            f"- Housing costs take {persona['housing_cost_pct_of_income']}% of household income"
        )

    lines += [
        "",
        "Write this person as JSON now. Remember: no ethnic, racial, cultural, or religious",
        "characterisation, and no mention of any product or purchase.",
    ]
    return "\n".join(lines)


def parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in response: {text[:200]}")
    return json.loads(cleaned[start : end + 1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--name-seed", type=int, default=7_312_026)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--tag", default="mixed", help="Which drawn set to write stories for.")
    args = parser.parse_args()

    if API_ENV_PATH.exists() and not os.getenv("OPENROUTER_API_KEY"):
        for line in API_ENV_PATH.read_text().splitlines():
            if line.startswith(("OPENROUTER_API_KEY=", "OPENROUTER_BASE_URL=")):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    client = load_llm_client()
    if not client.openrouter_api_key_available():
        raise SystemExit("OPENROUTER_API_KEY is not configured. Expected it in apps/api/.env")

    payload = json.loads((OUT_DIR / f"phase1_personas_{args.tag}.json").read_text())
    personas = payload["personas"]

    # Names first, from their own random stream, before the model sees anything.
    assigned = name_pool.assign_names([p.get("sex") for p in personas], args.name_seed)
    for persona, name in zip(personas, assigned):
        persona["name"] = name

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing {len(personas)} stories with {args.model}\n")

    for persona in personas:
        prompt = build_prompt(persona)
        digest = hashlib.sha256((args.model + prompt).encode()).hexdigest()[:16]
        cache_path = CACHE_DIR / f"{args.tag}_{persona['persona_id']}_{digest}.json"

        if cache_path.exists() and not args.force:
            story = json.loads(cache_path.read_text())
            source = "cached"
        else:
            text = client.generate_text_with_openrouter(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                model_name=args.model,
                temperature=args.temperature,
                max_tokens=1200,
            )
            story = parse_json_response(text)
            cache_path.write_text(json.dumps(story, indent=2))
            source = "generated"

        persona["story"] = story
        print(
            f"  {persona['persona_id']}  {persona['name']:<24} "
            f"{str(story.get('headline',''))[:52]:<54} [{source}]"
        )

    payload["name_assignment"] = (
        "Names are drawn at random from a fixed pool, independent of every persona attribute "
        f"except sex (seed {args.name_seed}). They carry no information about the household."
    )
    payload["story_model"] = args.model
    payload["field_provenance"] = {
        "census_grounded": [
            "age", "sex", "county", "puma", "marital_status", "education", "occupation",
            "employment_status", "hours_worked_per_week", "commute_mode", "commute_minutes",
            "household_income", "household_size", "children_in_household", "household_type",
            "tenure", "home_type", "bedrooms", "rooms", "year_built", "moved_in", "vehicles",
            "housing_cost_pct_of_income",
        ],
        "randomly_assigned": ["name"],
        "llm_written": [
            "headline", "biography", "daily_routine", "household_and_home",
            "priorities", "financial_picture", "free_time",
        ],
    }

    out_path = OUT_DIR / f"phase1_personas_{args.tag}_full.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
