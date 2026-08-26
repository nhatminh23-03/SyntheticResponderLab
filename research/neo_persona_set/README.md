# Neo Smart — grounded persona set

Standalone research pipeline. Generates 15 detailed personas for the **Tahoe Mini** ($23,000,
117 sq ft factory-built backyard studio), grounded in live US Census ACS microdata, including 2–3
who would decline the product.

Nothing here touches `apps/api` or `apps/web`. Wiring the winning model into the app is a separate,
later step.

## Why a model bake-off

The app's current "grounded" persona generator samples each trait block **independently**
(`_sample_grounded_traits_with_rng` in `legacy_runtime/backend/grounding/prior_sampler.py`), so the
joint distribution is a product of marginals — every real correlation between age, income, tenure,
and household size is lost. Downstream traits (lifestyle, use case, barrier, segment, fit tier) come
from `_pick_*` helpers keyed off the **loop index**, not from data.

This pipeline measures exactly how much that costs, and picks a better model on evidence.

## Setup

```bash
python3 -m venv ../.venv
../.venv/bin/pip install pandas numpy pyarrow scikit-learn openpyxl matplotlib requests python-dotenv
```

## Running

```bash
../.venv/bin/python 01_fetch_acs.py          # live Census download (~350 MB, no API key)
../.venv/bin/python 02_build_frame.py        # Southern California householder frame
../.venv/bin/python 03_compare_models.py     # the bake-off
../.venv/bin/python 04_select_personas.py    # pick 15, including the rejectors
../.venv/bin/python 05_write_narratives.py   # LLM narrative on the grounded skeletons
../.venv/bin/python 06_export_excel.py       # the workbook
```

`01_fetch_acs.py --vintage 1-year` downloads ~92 MB instead of ~350 MB for faster iteration.
`--only person|housing` re-fetches just one file.

## What each stage does

| Stage | Output |
|---|---|
| `01_fetch_acs.py` | `acs_person_slim.parquet`, `acs_housing_slim.parquet`, download manifest |
| `02_build_frame.py` | `socal_frame.parquet`, `frame_provenance.json`, `socal_pumas.csv` |
| `03_compare_models.py` | `model_comparison.{csv,json}`, `model_comparison_runs.csv` |
| `04_select_personas.py` | `persona_skeletons.json` |
| `05_write_narratives.py` | `personas_full.json` (+ cached narratives) |
| `06_export_excel.py` | `neo_smart_personas.xlsx` |

## Design decisions worth knowing

**The modelling frame keeps all tenures and home types.** Screening to owner + detached happens at
persona selection, not before. Filtering first would make `ownership` and `home_type` constant and
erase the joint structure the bake-off exists to measure. It also mirrors the real survey: a general
panel, then the S3 screen.

**Outdoor space is proxied by a detached single-family structure** (`BLD = 02`). ACS has no yard
variable. This is the pipeline's largest assumption and is printed in the workbook's Provenance sheet.

**`BLD` is recoded from the official PUMS dictionary, not from the app's mapping.** The app's
`build_grounding_features.py` maps `BLD in (1,2) → single_family_like`, but `BLD=1` is *mobile home*
and `BLD=3` is *one-family attached*. That mapping counts mobile homes as single-family and
townhouses as multifamily. `lib/recode.py` uses the correct codes; the app's version needs a
separate fix.

**Income is ADJINC-adjusted.** The 2024 5-Year file spans five income years with factors from
1.015250 to 1.222017 — ignoring it misstates income by up to 22%.

**Continuous detail comes from real donors.** The models generate categorical bundles; exact income,
age, and cost burden are hot-decked from a real weighted household matching that bundle, so every
number belongs to an actual Census record.

**`likely_response` is a transparent rule, not an LLM judgement.** See `lib/rejection.py`. Every
accept/unsure/reject label is reproducible from a persona's Census fields, and the contributing
reasons ship with the persona.

## Research isolation

Persona generation and narrative writing never read the AYTM questionnaire or report, the Tony
transcript, or anything under `Provided Info/`. The product description in `05_write_narratives.py`
is written inline from the public product concept. This keeps the Aug 29–31 synthetic-vs-real
validation uncontaminated, matching the constraint the app's own regression test enforces.

## What the fidelity numbers do and do not mean

The bake-off measures **demographic realism** — how well a generated population reproduces the joint
structure of held-out real Census households. It does **not** measure answer realism. No real survey
responses were used, and none are available in this repository. Whether these personas answer like
real respondents is the question the Aug 29–31 validation exists to answer.

## Phase 2

- Deep generative models (CTGAN, TVAE via SDV) — deferred; adds PyTorch and much longer training.
- Wire the winning sampler into `persona_generator.py`, replacing the independent draws.
- Replace the index-keyed `_pick_*` heuristics with data-driven assignment.
- Fix the `BLD` recode in `build_grounding_features.py`.
