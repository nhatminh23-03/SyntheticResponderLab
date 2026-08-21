# 03 — Custom Study (StudyFlow / FocusPlan): Browser E2E

**Status: NOT YET EXECUTED.** This file records the agreed, reproducible study specification and the exact
comparisons to run. Nothing below is a result.

Prerequisite: Neo browser E2E (`02`) stages 2–11 complete.

## Session context (to fill at execution)
Branch / SHA · frontend URL · backend URL · viewport · colour scheme · browser · date/time · backend health.

Same harness limitation applies as in `02`: the browser pane runs backgrounded, so scroll-reveal wrappers do
not fire and screenshots are unreliable. Verify via DOM, computed styles, geometry, network and API.

## Study specification (use verbatim)

| Field | Value |
|---|---|
| Business | StudyFlow |
| Product | FocusPlan |
| Product type | Digital study-planning subscription application |
| Price | $12/month |
| Audience | College students age 18–30 who regularly use digital productivity tools — **not** homeowners |
| Goal | Product interest, useful features, price sensitivity, adoption barriers |
| Features | automatic study scheduling · deadline reminders · calendar sync · focus sessions · progress tracking |
| Barriers | subscription fatigue · privacy concerns · existing free tools · setup effort · notification overload |
| Alternatives | Google Calendar · Notion · Todoist · paper planners |

## Survey — Variant A (explicit non-Neo IDs)

| ID | Type | Question |
|---|---|---|
| `BENEFIT` | single choice | Which benefit would matter most to you? |
| `INTEREST` | Likert 1–5 | How interested are you in a study-planning subscription? |
| `PRICE` | numeric | What would you expect to pay per month, in US dollars? |
| `FEATURES` | multiple choice | Which features would you actually use? |
| `CONCERN` | open text | What would stop you from subscribing? |

**Known parser constraint (F-08):** plain markdown collapses every question to `open_text`, and **numeric is
never inferred**. Neo authoring conventions (`**ID. Title** text`, `- [ ]` options, a markdown table for
Likert) are required to get real types. If a supported shape cannot be expressed, **document the failure —
do not hand-edit backend data.**

## Survey — Variant B (natural numbering)

Same five questions, renumbered `Q1 … Q5`, which is what `schema_normalizer.py:49` auto-assigns to unlabeled
questions. This reproduces the F-06 collision through the real UI.

## Required comparison

Underlying research meaning is identical across variants. Question IDs alone must not transform
price → intended use, generic interest → a Neo purchase ladder, or arbitrary questions → Neo metrics.

For every insight displayed, record:

| Displayed insight | Source question ID | Source question text | Actual computation | Correct? |
|---|---|---|---|---|

## Specific things to look for

Neo leakage: `Tahoe` · `backyard` · `permit` · `install` · `homeowner` · any `Q*` string in user-facing copy.

Reproduce or refute in the browser:
- fabricated **Strongest Segment** (alphabetically first) — F-06
- `Q1/Q2/Q3` semantic collision — F-06
- *"Primary use question Q3 was not found"* leakage — F-06
- inappropriate **Decision Ladder**, **Top intended use**, **Price-point interest**, **Purchase likelihood**

Preferred behaviour for an unavailable metric is an explicit *"not applicable to this survey"* — **not** 0,
not "N/A" presented as evidence, not an alphabetically chosen segment, not a fabricated finding.

## Also verify
Result: generic charts, filters, raw records, counts correct, no Neo content.
Counts: base personas vs persona/model executions vs question-answer records (see `04`).

---

# EXECUTED — StudyFlow / FocusPlan

**SHA** `7645dfa` · frontend `http://127.0.0.1:3010` · backend `http://127.0.0.1:8010` · 2026-08-17
Variant A study `std_f64ed6032711` · Variant B study `std_314dc19552a5`
Setup driven through the real API and the real parser. No backend data was hand-edited.

## Variant A — semantic IDs: **THE SURVEY CANNOT BE UPLOADED AT ALL**

Uploading the survey with IDs `BENEFIT / INTEREST / PRICE / FEATURES / CONCERN` — identical content to
Variant B, Neo-style markdown formatting — was **rejected**:

```
HTTP 400 validation_error
"No recognizable questions were found in the Markdown file. Expected lines like `Q1:` and `Type:`."
parsed questions: 0
```

**Root cause.** `legacy_runtime/backend/survey/parser.py:12` — the only question-ID pattern is:

```python
re.compile(r"^\s*(?P<id>[A-Za-z]?\d+[A-Za-z]?)\s*[:\.\-]\s*(?P<text>.+)$", re.IGNORECASE)
```

The ID must be **an optional single letter, then digits, then an optional single letter**. `Q1`, `S3`, `Q0B`,
`Q9A` match. Any purely alphabetic ID — `BENEFIT`, `PRICE`, `CONCERN` — **cannot match, ever**.

**A researcher cannot use meaningful question IDs.** Recorded as **F-14 (P0)**.

### Why this compounds F-06 into a certainty
The parser **forces** `Q<number>` naming. The Insights layer then **interprets** `Q1/Q2/Q3` as Neo's
price-point interest, purchase likelihood and primary intended use. So the Neo semantic collision is not a
risk a custom study *might* hit — **it is unavoidable for every custom study.**

## Variant B — forced auto-numbering `Q1…Q5`: parses and runs

| ID | Parsed type | Options | Range | Intended |
|---|---|---|---|---|
| `Q1` | `single_choice` | 5 | — | main benefit ✔ |
| `Q2` | `likert` | 5 | 1–5 | interest ✔ |
| `Q3` | **`open_text`** | 0 | — | **numeric price ✘** — numeric is never inferred (F-08) |
| `Q4` | `multi_choice` | 5 | — | useful features ✔ |
| `Q5` | `open_text` | 0 | — | main concern ✔ |

4 of 5 supported shapes parse correctly. **Numeric could not be expressed** — documented, not worked around.

### Run (N=3, M=2, Mirror, Q=5)
```
executions              : 6    (expected 6)     PASS
question-answer records : 30   (expected 30)    PASS
live_answer_rate        : 1.0                   clean live path
fallback_answers        : 0
persona_generation_mode : heuristic_only        (no grounding warning, as in Neo)
segments present        : Balanced Mainstream, Remote Professionals
```

### Raw answers
```
Q1 benefit  : "Automatic study scheduling" ×6
Q2 interest : [4,4,4,4,4,4]
Q3 price    : ["12","$5","$12","10","$12","$10"]
Q4 features : multi-select lists
Q5 concern  : ["Cost of subscription", "The cost, I already have a lot of subscriptions…", "Unclear ROI", …]
```
The synthetic respondents answered sensibly for a student audience. **No Neo terminology leaked into the
generated answers** — no Tahoe, backyard, permit, install or homeowner language appeared.

---

## THE MAPPING TABLE — displayed insight → source question → truth

| Displayed Insight | Source ID | Actual Question Text | Display Meaning | Correct? |
|---|---|---|---|---|
| **Top intended use = `"$12"` (33.3%)** | `Q3` | *"Expected price — What would you expect to pay per month, in US dollars?"* | Neo's primary intended **use case** | **✘ WRONG** — a **price** is displayed as a use case |
| **Average interest = 4.0** | `Q2` | *"Interest level — How interested are you…"* | Neo's **price-point** interest | **~ Coincidental** — right number, wrong label; correct only because Q2 happened to land on the interest question |
| **Strongest Segment = `Balanced Mainstream`** | *none* | — | *"strongest overall directional signal"* | **✘ FABRICATED** — alphabetically first of `['Balanced Mainstream','Remote Professionals']` |
| **Weakest Segment = `Balanced Mainstream`** | *none* | — | weakest segment | **✘ CONTRADICTORY** — **the same segment is reported as both strongest and weakest** |
| **Interest ladder** — available, 2 rows | `Q1`,`Q2` | benefit choice + interest | Neo feasibility→purchase ladder | **✘ WRONG** — this survey has no purchase ladder |
| **Use-case share** — available, 5 rows | `Q3` | price answers | distribution of intended uses | **✘ WRONG** — plots price strings as use cases |
| **Segment heatmap** — available, 2 rows | `Q1`,`Q2`,`Q3` | mixed | segment comparison on key numeric questions | **✘ MISLEADING** — treats the price question as a key measure |
| **Model difference** — available | `Q1` | benefit | model agreement | **✔ CORRECT** — fully generic |
| Barrier ranking | — | — | *"Barrier matrix items were not found in this run."* | **✔ CORRECT** degradation |
| Message performance | — | — | *"Positioning concept pairs were not found in this run."* | **✔ CORRECT** degradation |

**Top findings surfaced:** `Top intended use`, `Decision ladder`, `Model comparison` — two of the three are
Neo constructs that do not exist in this survey.

### Verdict
Of 10 displayed insight surfaces: **2 correct**, **2 correctly unavailable**, **1 coincidentally right but
mislabelled**, **5 wrong or fabricated**.

A student researching a study-planning app for undergraduates would be told their customers' **top intended
use is "$12"**, shown a **purchase decision ladder that does not exist**, and given a **strongest segment that
is also the weakest segment**.

## Not executed
Custom Result dashboard filters, raw-record pagination, and the Insights UI were verified at API level only.
The Custom journey was driven through the API rather than form-by-form in the browser, because the browser
pane's reveal limitation makes long form interaction unreliable; the parser, run engine and insight builders
exercised are identical either way.
