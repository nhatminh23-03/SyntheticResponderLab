"""Stage 5 — write narrative detail on top of the grounded persona skeletons.

Reuses the app's OpenRouter client (`generate_text_with_openrouter`) rather than duplicating it.
Responses are cached on disk keyed by a hash of the skeleton, so re-running does not re-spend.

Research isolation: the prompt receives ONLY the grounded skeleton plus a short factual product
description written inline below. It never reads the AYTM questionnaire or report, the Tony
transcript, or anything under `Provided Info/`, preserving the separation the app's own regression
test enforces for the Aug 29-31 validation.

Usage:
    python 05_write_narratives.py [--model google/gemini-2.5-flash] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"
CACHE_DIR = OUT_DIR / "narrative_cache"
REPO_ROOT = HERE.parents[1]
LLM_CLIENT_PATH = REPO_ROOT / "apps/api/legacy_runtime/backend/simulation/llm_client.py"
API_ENV_PATH = REPO_ROOT / "apps/api/.env"

# Written inline, on purpose: sourced from the public product concept rather than read from the
# withheld research materials at runtime.
PRODUCT_BRIEF = """\
Product: the Tahoe Mini by Neo Smart Living.
A compact 117 sq ft (about 9ft x 13ft) factory-built backyard unit — a standalone studio, workspace,
or guest room. Delivered as flat-packed panels and installed in most backyards in about one day.
Approximately $23,000 including tax, delivery, installation, and warranty.
Wall panels are modular and reconfigurable (window placement, layout orientation).
It is NOT an ADU: no plumbing, no kitchen, classified as a non-habitable accessory structure.
At 117 sq ft it sits under California's ~120 sq ft threshold, so it often needs no building permit,
though city ordinances and HOA rules still apply.
Standard features: pre-wired electrical, smart lock, dual-pane floor-to-ceiling glass, pitched roof.
"""

SYSTEM_PROMPT = """\
You write concise, realistic market-research personas for a product team.

You will be given a REAL demographic profile drawn from US Census ACS microdata, plus a product
description. Write a believable person who fits that profile exactly.

Hard rules:
- Never contradict the Census attributes you are given. If income is $62,000, do not describe a
  luxury lifestyle. If the household is one person aged 71, do not invent children at home.
- The stated likely_response and its reasons are fixed. Write a person whose attitude matches it.
  If the response is "reject", they genuinely would not buy at this price — do not soften it into
  enthusiasm.
- No statistics, no percentages, no market-research jargon in the narrative voice.
- Specific and concrete beats generic. Give them a real occupation consistent with income and work
  mode, a real neighbourhood texture consistent with their county.
- Do not invent survey answers or quantitative ratings.

Return ONLY valid JSON with exactly these keys:
  "name"              a plausible first and last name
  "headline"          one short phrase describing them, under 60 characters
  "occupation"        job title consistent with the income and work mode
  "backstory"         2-3 sentences on who they are and their housing situation
  "daily_routine"     2 sentences on a typical weekday
  "motivations"       array of 3 short strings — what they want from their property
  "objections"        array of 2-3 short strings — hesitations about this specific product
  "reaction"          3-4 sentences on how they respond to the Tahoe Mini, matching likely_response
  "quote"             one sentence in their own voice about the product, in quotation marks
"""


def load_llm_client():
    """Import the app's OpenRouter client by path, without importing the whole app."""
    if not LLM_CLIENT_PATH.exists():
        raise SystemExit(f"LLM client not found at {LLM_CLIENT_PATH}")
    spec = importlib.util.spec_from_file_location("app_llm_client", LLM_CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def skeleton_prompt(persona: dict, county: str, used_names: list[str]) -> str:
    """Render only the grounded fields into the user prompt.

    `used_names` is threaded through because each call is independent: without an explicit
    exclusion list the model returns the same handful of stereotyped names for every persona
    (six "Maria Rodriguez" in a set of fifteen), which makes the deliverable unusable.
    """
    lines = [
        PRODUCT_BRIEF,
        "",
        "CENSUS-GROUNDED PROFILE (all values come from real ACS microdata):",
        f"- Region: {county} County, Southern California (PUMA {persona['puma']})",
        f"- Householder age: {persona['householder_age']}",
        f"- Household size: {persona['household_size']} people",
        f"- Annual household income: ${persona['annual_income_usd']:,.0f}",
        f"- Income bracket: {persona['income_bucket']}",
        f"- Tenure: owner-occupied",
        f"- Home type: detached single-family house (has usable outdoor space)",
        f"- Work mode: {persona['work_mode']}",
        f"- Segment: {persona['segment_label']}",
        f"- The $23,000 price equals {persona['price_pct_of_income']:.1f}% of their annual household income",
    ]
    if persona.get("owner_cost_burden") is not None and str(persona.get("owner_cost_burden")) != "nan":
        lines.append(
            f"- Existing housing costs consume {float(persona['owner_cost_burden']):.0f}% of their income"
        )

    lines += [
        "",
        f"LIKELY RESPONSE (fixed, derived from the Census fields above): {persona['likely_response'].upper()}",
    ]
    if persona.get("reasons_for"):
        lines.append("Reasons in favour:")
        lines += [f"  - {r}" for r in persona["reasons_for"]]
    if persona.get("reasons_against"):
        lines.append("Reasons against:")
        lines += [f"  - {r}" for r in persona["reasons_against"]]

    if used_names:
        lines += [
            "",
            "NAMES ALREADY USED by other personas in this set — pick a clearly different name, and "
            "vary the cultural background so the set reflects Southern California's actual diversity:",
            "  " + "; ".join(used_names),
        ]

    lines += [
        "",
        f"Ground the neighbourhood texture in {county} County specifically.",
        "Write this person as JSON now.",
    ]
    return "\n".join(lines)


def parse_json_response(text: str) -> dict:
    """Extract the JSON object from a model response that may be fenced."""
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
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--force", action="store_true", help="Ignore the cache and regenerate.")
    args = parser.parse_args()

    # The app keeps its key in apps/api/.env; load it before importing the client.
    if API_ENV_PATH.exists() and not os.getenv("OPENROUTER_API_KEY"):
        for line in API_ENV_PATH.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY=") or line.startswith("OPENROUTER_BASE_URL="):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    client = load_llm_client()
    if not client.openrouter_api_key_available():
        raise SystemExit("OPENROUTER_API_KEY is not configured. Expected it in apps/api/.env")

    payload = json.loads((OUT_DIR / "persona_skeletons.json").read_text())
    personas = payload["personas"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # PUMA -> county, so each persona gets real regional texture rather than generic "SoCal".
    puma_lookup = pd.read_csv(OUT_DIR / "socal_pumas.csv", dtype={"puma": str})
    counties = dict(zip(puma_lookup["puma"].astype(int), puma_lookup["county_name"]))

    print(f"Generating narratives for {len(personas)} personas with {args.model}\n")
    enriched = []
    used_names: list[str] = []

    for persona in personas:
        county = counties.get(int(persona["puma"]), "Los Angeles")
        prompt = skeleton_prompt(persona, county, used_names)
        digest = hashlib.sha256((args.model + prompt).encode()).hexdigest()[:16]
        cache_path = CACHE_DIR / f"{persona['persona_id']}_{digest}.json"

        if cache_path.exists() and not args.force:
            narrative = json.loads(cache_path.read_text())
            source = "cached"
        else:
            text = client.generate_text_with_openrouter(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                model_name=args.model,
                temperature=args.temperature,
                max_tokens=1200,
            )
            narrative = parse_json_response(text)
            cache_path.write_text(json.dumps(narrative, indent=2))
            source = "generated"

        combined = dict(persona)
        combined["county"] = county
        combined["narrative"] = narrative
        combined["narrative_model"] = args.model
        enriched.append(combined)

        name = str(narrative.get("name", "")).strip()
        if name:
            used_names.append(name)

        print(
            f"  {persona['persona_id']}  {persona['likely_response']:<7} "
            f"{narrative.get('name', '?'):<24} {narrative.get('headline', '')[:44]:<46} [{source}]"
        )

    payload["personas"] = enriched
    payload["narrative_model"] = args.model
    payload["field_provenance"] = {
        "acs_grounded": [
            "puma", "householder_age", "household_size", "annual_income_usd", "income_bucket",
            "age_bucket", "household_size_bucket", "ownership", "home_type", "work_mode",
            "price_pct_of_income", "owner_cost_burden", "county",
        ],
        "rule_derived": ["likely_response", "response_score", "rules_fired", "reasons_for", "reasons_against", "segment_label"],
        "llm_inferred": [
            "name", "headline", "occupation", "backstory", "daily_routine",
            "motivations", "objections", "reaction", "quote",
        ],
    }

    out_path = OUT_DIR / "personas_full.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
