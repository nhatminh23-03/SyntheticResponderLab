"""Write a persona file whose story text carries no money cue, for a clean income ablation.

R012 through R014c removed the named income fields and concluded the model must be inferring income
from occupation and education. That conclusion was not supported: the story sections those runs kept
still carried income. In the S1 panel, 6 of 100 personas have their exact household income written
out as a number in the kept text, 62 mention income or salary, and 95 contain some money language.
Only 5 were genuinely clean, far too few to test anything.

This removes the cue at the sentence level rather than the field level: any sentence in a story
section that mentions money is dropped, and the remaining sentences are rejoined. Sentence-level is
the right granularity because a single sentence usually carries one thought, so dropping it leaves
prose that still reads, where dropping a word leaves a hole the model can see.

`--report` prints what remains without writing anything, which is how the result is checked: the
audit at the end counts any surviving cue and fails loudly rather than quietly shipping a condition
that did not strip what it claimed to.

    apps/api/.venv/bin/python research/neo_persona_set/phase3/strip_money_language.py \
        --personas out/phase1_interview_matched600_s1.csv \
        --out out/phase1_interview_matched600_s1_nomoney.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

STORY_PREFIX = "story_"

# Any of these in a sentence is enough to drop it. Deliberately wide: a false positive costs one
# sentence of colour, a false negative leaves an income cue in a condition whose entire claim is
# that there is no income cue.
MONEY = re.compile(
    r"(\$|\b\d{2,3},\d{3}\b|\b(income|salary|salaried|wage|wages|earn|earns|earned|earning|earnings|"
    r"paycheck|pay|paid|budget|budgets|budgeting|afford|affordable|affording|affordability|"
    r"mortgage|rent|rents|renting|savings|saved|saving|debt|debts|loan|loans|bill|bills|"
    r"cost|costs|costly|expense|expenses|expensive|cheap|cheaper|price|priced|pricing|"
    r"financ\w*|dollar|dollars|money|thrift\w*|frugal\w*|penny|pennies|invest\w*|"
    r"retirement fund|pension|insurance|premium|tax|taxes|discount|bargain|splurge|"
    r"paycheque|wealth\w*|rich|poor|broke|tight)\b)",
    re.IGNORECASE,
)

# Split on sentence-ending punctuation followed by a space. Keeps the punctuation with the sentence.
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def strip_text(text: str) -> Tuple[str, int]:
    """Drop every sentence mentioning money. Returns the survivors and how many were dropped."""
    if not text or not text.strip():
        return text, 0
    sentences = SENTENCE.split(text.strip())
    kept = [s for s in sentences if not MONEY.search(s)]
    return " ".join(kept), len(sentences) - len(kept)


def strip_list_field(text: str) -> Tuple[str, int]:
    """priorities is a semicolon-separated list, so items are dropped rather than sentences."""
    items = [i.strip() for i in text.split(";") if i.strip()]
    kept = [i for i in items if not MONEY.search(i)]
    return "; ".join(kept), len(items) - len(kept)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--personas", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", action="store_true", help="print the audit, write nothing")
    args = parser.parse_args()

    with args.personas.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    story_columns = [c for c in header if c.startswith(STORY_PREFIX)]

    dropped_by_column: Dict[str, int] = {c: 0 for c in story_columns}
    emptied: List[str] = []
    for row in rows:
        for column in story_columns:
            original = row.get(column) or ""
            if not original.strip():
                continue
            if column == f"{STORY_PREFIX}priorities":
                new, dropped = strip_list_field(original)
            else:
                new, dropped = strip_text(original)
            row[column] = new
            dropped_by_column[column] += dropped
            if original.strip() and not new.strip():
                emptied.append(f"{row['persona_id']}/{column[len(STORY_PREFIX):]}")

    # --- audit: does any cue survive? ------------------------------------------------------
    survivors: List[str] = []
    for row in rows:
        text = " ".join((row.get(c) or "") for c in story_columns)
        hit = MONEY.search(text)
        if hit:
            survivors.append(f"{row['persona_id']}: {hit.group(0)!r}")

    print(f"{len(rows)} personas, {len(story_columns)} story sections")
    print(f"sentences or list items dropped, by section:")
    for column, count in sorted(dropped_by_column.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"  {column[len(STORY_PREFIX):]:<22}{count:>5}")
    print(f"sections emptied completely: {len(emptied)}"
          + (f" (e.g. {', '.join(emptied[:4])})" if emptied else ""))
    print(f"personas with a surviving money cue: {len(survivors)}")
    for line in survivors[:10]:
        print(f"  {line}")

    if survivors:
        print("\nREFUSED: the point of this file is that no money cue remains. Widen MONEY and rerun.",
              file=sys.stderr)
        return 1
    if args.report or args.out is None:
        return 0

    # No BOM: the phase-1 exporter writes plain utf-8 and persona_census_lookup opens
    # the persona file as utf-8, so a BOM turns the first column name into "\ufeffpersona_id".
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
