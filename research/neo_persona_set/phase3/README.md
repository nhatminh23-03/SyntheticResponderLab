# Phase 3 — synthetic runs vs the real AYTM survey

Compares each phase-2 run with the real 600-respondent AYTM export, question by question, offline.
Only `realdata.py` opens the real file and only when `--real` is passed; nothing in phase 2 imports
phase 3 (a test enforces it), and no output is ever written into the raw-data folder (exit 3).

## Run (from the repository root)

```bash
ASSETS=../SyntheticResponderLab-Assets
REAL="$ASSETS/raw 600-participant dataset and a sample report from aytm/survey-760085-2026-03-25-raw-data.csv"
RUNS=$ASSETS/match_600_persona/survey_runs
apps/api/.venv/bin/python research/neo_persona_set/phase3/filter_qualified.py --runs $RUNS/*_matched
apps/api/.venv/bin/python research/neo_persona_set/phase3/compare_real.py --real "$REAL" \
  --runs $RUNS/*_matched --out $ASSETS/match_600_persona/real_comparison/$(date -u +%Y%m%dT%H%MZ)
```

Flags: `--require-outdoor-space` (default; drops synthetic personas whose S3 starts with "No", about
31% of the matched set) / `--keep-all`, `--close-tv 0.10`, `--exclude-fallback`.

## Method

`crosswalk.py` maps our 39 ids to the AYTM columns (our Q1 = real Q6, Q5_1..7 = Q9 matrix rows,
Q15..17 = Q30 rows 1..3, Q26 derived from the Q37 club multi-select, Q21/Q22 from Age/Income).
Q7 and Q23 have no counterpart; Q30 is reported, not scored. Categories are the options both
surveys share; real-only options (Q11 Other, Q31 Smart Technology/Showroom/Other, six Q33
channels) and our-only options (Q22 Prefer not to say) are reported as off-list shares. Per run x
question: TV distance, JS divergence, Spearman on option shares, top-option match, likert means and
their difference, chi-square GOF p (hand-rolled), `close` = TV <= threshold. Per option: shares and
a two-proportion z-test.

## Outputs (`--out`)

| File | Contents |
| --- | --- |
| `comparison_long.csv` | one row per run x question |
| `comparison_options.csv` | one row per run x question x category |
| `comparison_summary.csv` | per run: questions compared/close, mean/median TV, mean JS, top-match share, mean abs likert diff |
| `comparison_by_question.md` | real vs each run side by side |
| `unmapped.md` | items without counterpart on either side |
| `crosswalk.csv` | the mapping with both option lists |
| `manifest.json` | sha256 of inputs and outputs, filters, thresholds, N per run, git commit |

## Other tools

`lint_personas.py` (checks a persona CSV), `select_panel.py` (stratified 150-persona panel),
`add_bom.py` (Excel-safe rewrite of old run CSVs), `registry.py` (hypothesis registry),
`write_start_here.py` (START_HERE.md for the shared folder), `make_mixed_panel.py` (one persona per
arm across several runs), `spread_diagnostics.py` (spread and the income gradient), `judge_reasons.py` (a third model
picks the better-reasoned answer between two `--reason-per-answer` runs; needs the API). Tests:
`apps/api/.venv/bin/python -m pytest research/neo_persona_set/phase3 -q`.

## Scoring standard: Dr. Lin's calibration / validation split

Adopted 2026-09-30. Anything fitted to real answers (driver donors, model adjustments) uses only the
calibration items and the fit half of respondents; results are scored only on the 13 validation
items against the other 300. Every headline number from now on is on this standard.

```bash
# 1. convert her split (DrLinSplit/aytm_respondent_split_ids.csv) into Response-ID files.
#    Her ids are row indexes: aytm_N = respondent row N of the raw file, in file order.
#    Written outside the repo; the script refuses the repo and the real-data folder.
apps/api/.venv/bin/python research/neo_persona_set/phase3/make_real_split.py --real "$REAL" \
  --from-lin ../SyntheticResponderLab-Assets/DrLinSplit/aytm_respondent_split_ids.csv \
  --out ../SyntheticResponderLab-Assets/real_splits/lin-seed42

# 2. score only the 13 validation items, against only her 300 val respondents
apps/api/.venv/bin/python research/neo_persona_set/phase3/compare_real.py --real "$REAL" \
  --runs <run_dir> ... --out <dir> \
  --items lin13-validation \
  --real-ids ../SyntheticResponderLab-Assets/real_splits/lin-seed42/score_ids.txt
```

- `--items` takes a named set from `item_sets.py` (`lin13-validation`, `lin13-calibration`,
  `all-scored`) or a file of question ids. Questions outside the set are still compared and
  reported, with `scored=false`. Without `--items` every comparable question counts, as before.
- The named sets match her `item_split.csv` (`item_sets.LIN_ITEM_NAMES` translates her names).
  Q15 and Q24 are set aside (Dr. Wang, 2026-09-24) and are in no named set; `all-scored` is the
  other 34. On our survey the calibration set has 10 items, not 13: our survey carries only 3 of
  the 5 value drivers and Q15 is set aside.
- `--real-ids` takes a file of AYTM Response IDs. `real_splits/lin-seed42/` is her split;
  `real_splits/provisional-seed42/` was a stand-in drawn before hers arrived and is superseded.
  Without `--from-lin`, `make_real_split.py` still draws a new seeded split.
- `comparison_summary.csv` gains `item_set` and `n_real_respondents`; `manifest.json` records the
  item list and the id file's hash.

## Hybrid runs (driver personas)

Dr. Lin's driver method gives each persona four answers copied from a real respondent in the
calibration half with the same income band, age group and kids: prior consideration (Q0A), primary
use (Q3), outdoor recreation (Q25) and club membership (Q26). Real answers then reach the prompt,
so these runs are labelled hybrid end to end:

1. Dr. Lin's persona files (`DrLinSplit/personas_S*_drv.csv`) are the team's persona file plus
   `prior_consideration_of_backyard_unit`, `outdoor_recreation_frequency`,
   `member_of_outdoor_club`, `most_likely_use_for_a_backyard_unit` and `driver_donor_id` (an
   `aytm_N` row id, never sent to the model). The runner refuses such a file without `--hybrid`,
   and `--hybrid` needs `hybrid` in the run tag (`phase2/README.md`).
2. `make_mixed_panel.py` deals personas to arms that must share the persona file, seed, answer
   mode, persona kind and style mix (`--allow-mismatch trait_mix` to mix styled and unstyled on
   purpose); `probabilities.csv` is carried for `--answer-mode distribution` arms.
3. `compare_real.py` refuses a hybrid run without `--real-ids` or with any of the four driver
   items in the scored set (`item_sets.LIN_DRIVERS`).

Pre-registered: R020 (unstyled four-model mix) and R020b (styled), in `registry.csv`.
