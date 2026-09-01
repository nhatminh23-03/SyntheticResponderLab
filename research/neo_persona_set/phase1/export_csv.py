"""Phase 1, step 4 — flatten the personas to CSV.

One row per persona, every field in one place. Column names are prefixed so the source of each
value is obvious at a glance:

    census_*  taken from the household's own ACS record
    story_*   written by the language model
    name      assigned at random, carries no information

A second file records the method, so the CSV never travels without its provenance.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "out"

CENSUS_FIELDS = [
    "age", "sex", "county", "puma", "marital_status", "education", "occupation",
    "employment_status", "hours_worked_per_week", "commute_mode", "commute_minutes",
    "household_income", "household_size", "children_in_household", "household_type",
    "tenure", "home_type", "bedrooms", "rooms", "year_built", "moved_in", "vehicles",
    "housing_cost_pct_of_income", "census_id", "census_weight",
]

STORY_FIELDS = [
    "headline", "biography", "daily_routine", "household_and_home",
    "priorities", "financial_picture", "free_time",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="mixed")
    args = parser.parse_args()

    payload = json.loads((OUT_DIR / f"phase1_personas_{args.tag}_full.json").read_text())
    personas = payload["personas"]

    header = ["persona_id", "name"]
    # census_id / census_weight already carry the prefix; avoid "census_census_id".
    header += [f if f.startswith("census_") else f"census_{f}" for f in CENSUS_FIELDS]
    header += [f"story_{f}" for f in STORY_FIELDS]

    out_path = OUT_DIR / f"phase1_personas_{args.tag}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)

        for persona in personas:
            row = [persona["persona_id"], persona.get("name")]
            row += [persona.get(field) for field in CENSUS_FIELDS]

            story = persona.get("story", {})
            for field in STORY_FIELDS:
                value = story.get(field)
                # Lists (priorities) become one cell, semicolon separated, so the CSV stays flat.
                row.append("; ".join(str(v) for v in value) if isinstance(value, list) else value)
            writer.writerow(row)

    # Provenance travels with the data rather than living only in someone's memory.
    method_path = OUT_DIR / f"phase1_method_{args.tag}.txt"
    lines = [
        "NEO SMART — PHASE 1 PERSONA SET",
        "=" * 70,
        "",
        "METHOD",
        payload["method"],
        "",
        "SCREENS APPLIED (in order)",
    ]
    for key, description in payload["screens"].items():
        lines.append(f"  {key:<12} {description}")

    lines += [
        "",
        "FUNNEL",
    ]
    for step in payload["funnel"]:
        households = f"{step['weighted_households']:,} households" if step["weighted_households"] else ""
        lines.append(f"  {step['step']:<52} {step['records']:>9,} records   {households}")

    lines += [
        "",
        f"ELIGIBLE POOL   {payload['eligible_pool_records']:,} records "
        f"({payload['eligible_pool_households']:,} California households)",
        f"DRAWN           {payload['drawn']} at random, seed {payload['seed']}",
        "",
        "BIAS CONTROLS",
        f"  {payload['excluded_by_design']}",
        f"  {payload['name_assignment']}",
        "  Stories are checked by phase1/audit_bias.py for any mention of ethnicity, immigration,",
        "  religion, language, or nationality, and for judgement-loaded language that tracks income.",
        "",
        "FIELD PROVENANCE",
    ]
    for source, fields in payload["field_provenance"].items():
        lines.append(f"  {source}:")
        lines.append(f"    {', '.join(fields)}")

    lines += [
        "",
        "NOT INCLUDED, DELIBERATELY",
        "  No product reaction or purchase intention appears in any story. These personas will",
        "  answer a survey later; pre-writing their opinion would bias that answer and make any",
        "  comparison against the real respondents circular.",
        "",
        f"Story model: {payload['story_model']}",
    ]
    method_path.write_text("\n".join(lines))

    print(f"Wrote {out_path.name}  —  {len(personas)} rows x {len(header)} columns")
    print(f"Wrote {method_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
