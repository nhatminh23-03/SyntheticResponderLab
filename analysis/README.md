# Validation analysis

This is the R project for the three validation arms and their reproducible report. Open
`SyntheticResponderLab-analysis.Rproj`, then restore the pinned environment from the repository
root with:

```r
renv::restore(project = "analysis")
```

The initial P4.1 suite uses only base R. Add a package to `renv.lock` in the same change that first
uses it.

## Complete reproducible report

`run_all.R` rebuilds every implemented validation component in memory and writes one self-contained
HTML report. It does not read prior files from `analysis/output/`. The report includes Arm A, Arm B,
Arm C (256 respondents and 42 shared questions), all five held-out non-LLM baselines, every registered question
test and per-estimand TOST result, fixed-seed provenance, and input checksums. It contains aggregate
results only and makes no model or provider calls.

For the zero-argument command, place the local, ignored inputs at these paths:

- `analysis/data/arm_a_housing.parquet` and `analysis/data/arm_a_person.parquet` — California PUMS
- `analysis/data/arm_b_housing.parquet` and `analysis/data/arm_b_person.parquet` — nationwide PUMS
- `analysis/data/real_responses.csv` — the read-only real panel source (do not copy it into prompts)
- `analysis/data/synthetic_responses.csv` — the synthetic response comparison sample
- `analysis/data/question_registry.csv` — the frozen 32-item test registry
- `~/dev/aytm-real-data/neo_smart_living/student_sample/{student_CLEAN.csv,aytm_CLEAN.csv,Question_Mapping.csv}` — read-only Arm C sources
- `analysis/data/arm_c_synthetic_responses.csv` — independently produced answers for the
  fixed `ARM_C_SEED` draw, IDs `arm_c_001` through `arm_c_256`, using audited common coding
- `analysis/data/arm_c_question_registry.csv` — pre-registered types and equivalence margins for
  every quantitative matched question; excludes audited multi-select/open-ended items

Then run:

```sh
/usr/local/bin/Rscript analysis/run_all.R
```

The report is rebuilt at `analysis/output/validation_report.html`. Defaults assume `Response ID` and
`synthetic_id` ID columns, `Gender,Household Income,State` strata, and
`Age,Gender,Household Income,State` k-NN predictors. All paths and column selections can be supplied
explicitly without making seeds configurable:

```sh
/usr/local/bin/Rscript analysis/run_all.R \
  --arm-a-housing /read-only/california/acs_housing_slim.parquet \
  --arm-a-person /read-only/california/acs_person_slim.parquet \
  --arm-b-housing /read-only/national/acs_housing_slim.parquet \
  --arm-b-person /read-only/national/acs_person_slim.parquet \
  --real /read-only/neo_smart_living/real-responses.csv \
  --synthetic /local/synthetic-responses.csv \
  --registry /local/question-registry.csv \
  --real-id "Response ID" \
  --synthetic-id synthetic_id \
  --strata "Gender,Household Income,State" \
  --knn "Age,Gender,Household Income,State" \
  --output analysis/output/validation_report.html
```

Arm C uses the Arm B PUMS inputs and accepts `--arm-c-student`, `--arm-c-aytm`,
`--arm-c-mapping`, `--arm-c-synthetic`, and `--arm-c-registry` path overrides. Missing inputs fail
explicitly. The report includes its demographic calibration and margins, all 42 harmonization
decisions, per-item missingness, tests, TOST results, and screening/geography caveats. AYTM coding
is used locally; student responses are the reference for Arm C tests. P4.7 interview-theme
validation is also identified as outside this quantitative report rather than represented by a
placeholder statistic.

## Layout

- `R/` contains reusable analysis functions.
- `data/` is for local analysis inputs. Its contents are ignored; real survey responses stay in
  their read-only external location and must never be copied into model prompts.
- `output/` contains reproducible generated artifacts and is ignored.
- `tests/` contains base-R assertion files named `test_*.R`. `tests/test_all.R` discovers them and
  is the entry point used by `scripts/verify.sh`.
- Top-level `*.R` files are runnable analysis entry points.

## Non-LLM respondent baselines

`run_non_llm_baselines.R` implements the marginal sampler, multivariate normal, Gaussian copula,
stratum mean, and five-nearest-neighbour lookup baselines for the frozen 32-item instrument. The
input contract is deliberately strict: exactly 600 rows, one unique respondent ID, exactly 32
complete numeric item columns, and explicit demographic columns for strata and distance. It uses a
fixed-seed 300/300 split, fits every model on the first half, and scores only against the held-out
half. Every prediction path rejects IDs that appeared during fitting.

Pass comma-separated column names from the local read-only real-data CSV. For example (replace the
column names with the coded instrument's actual headers):

```sh
/usr/local/bin/Rscript analysis/run_non_llm_baselines.R \
  --input /path/to/read-only/real-600.csv \
  --id respondent_id \
  --items Q1,Q2,Q3,Q4,Q5,Q6,Q7,Q8,Q9,Q10,Q11,Q12,Q13,Q14,Q15,Q16,Q17,Q18,Q19,Q20,Q21,Q22,Q23,Q24,Q25,Q26,Q27,Q28,Q29,Q30,Q31,Q32 \
  --strata region,age_band,income_band \
  --knn age,income,region,gender \
  --output analysis/output/non_llm_baselines
```

The ignored output directory receives one synthetic-response CSV per baseline plus aggregate
mean-, standard-deviation-, and correlation-RMSE metrics and a held-out audit. Source respondent IDs
are replaced with positional held-out IDs in written predictions. The real held-out answers are
used only for local R evaluation; this workflow has no model/provider calls and no prompt path.

## Registered question-type test battery

`run_test_battery.R` compares one real response file with one synthetic response file using a
question registry that must be frozen before examining comparison results. The registry has one row
per pre-coded analyzable item and the columns `question_id`, `question_type`,
`equivalence_margin`, and (for binary items) `positive_level`. Supported types are:

- `continuous`: Welch two-sample t-test, raw mean difference with a 95% CI, Hedges' g with an
  approximate 95% CI, and a Welch TOST on the raw-unit margin.
- `binary`: two-sample unpooled Wald z-test and risk difference with a 95% CI; TOST uses the
  registered absolute risk-difference margin. Pre-code each multi-select option as its own binary
  item.
- `categorical`: Pearson chi-square test and Cramer's V with a fixed-seed bootstrap standard-error 95%
  CI. TOST is applied to every category's proportion difference, and the question is equivalent
  only if every category passes the registered absolute proportion-difference margin.

Likert items must be registered according to the analysis decision made before seeing results:
`continuous` when numeric spacing is being treated as meaningful, otherwise `categorical`. The
runner does not infer types or margins from observed answers. At alpha 0.05, TOST reports the
corresponding 90% CI. Small expected cells are retained for the requested Wald/chi-square battery
but explicitly flagged in `assumption_note`.

```sh
/usr/local/bin/Rscript analysis/run_test_battery.R \
  --real /read-only/real-responses.csv \
  --synthetic analysis/output/synthetic-responses.csv \
  --registry analysis/question-test-registry.csv \
  --real-id respondent_id \
  --synthetic-id synthetic_id \
  --output analysis/output/test_battery
```

The output contains `test_results.csv`, per-estimand `tost_details.csv`, the exact validated registry
snapshot, and provenance including a registry checksum. It never writes respondent-level real
answers and has no model/provider call or prompt path.

## Arm A: hard-screened draw

`run_arm_a.R` reuses the three PUMS screens in `screen_counts.R`, then makes one reproducible,
`WGTP`-weighted draw of 600 California households without replacement. The seed is fixed in code
at `20260904`; it is deliberately not a command-line option. It compares the draw with the 600
completed real-panel respondents on harmonized age, income, gender, geography, outdoor-space
screen/proxy, and combined hard-screen eligibility.

For the real panel's frozen PQ1 screener, both “Yes” and “I'm not sure, but possibly” pass: either
response says the structure could potentially be placed, and both routes reached the completed
survey. This preserves the SPEC's documented approximately 21% real-panel hard-screen pass rate.

The real file is read locally and only aggregate comparison counts leave the analysis process. The
individual output contains synthetic PUMS respondents only, and this script has no model/provider
call or prompt path.

```sh
/usr/local/bin/Rscript analysis/run_arm_a.R \
  --housing /read-only/pums/acs_housing_slim.parquet \
  --person /read-only/pums/acs_person_slim.parquet \
  --real /read-only/neo_smart_living/survey-760085-2026-03-25-raw-data.csv \
  --output analysis/output/arm_a
```

Parquet input uses the same optional `arrow` dependency as `screen_counts.R`. The output directory
contains the 600-row synthetic draw, aggregate categorical and age comparisons, the screen audit,
the PUMS funnel, and provenance recording the fixed seed and data-isolation rule.

## Arm B: distribution-matched draw

`run_arm_b.R` builds an unscreened frame of occupied adult PUMS householders and uses iterative
proportional fitting (raking) to match the observed real-panel margins for age band, gender,
household-income band, and state. Raking starts from `WGTP`, must converge within a fixed tolerance,
and is followed by a reproducible, quota-balanced 600-person draw without replacement. The emitted
draw must reproduce every observed marginal count exactly; it fails if the joint PUMS support cannot
realize those margins. The seed is fixed in code at `20260904` and cannot be changed from the command
line.

Because the real 600 is national, Arm B requires nationwide PUMS housing and person inputs (for
example, the state PUMS extracts concatenated with their original `ST` fields). The California-only
files created by `research/neo_persona_set/01_fetch_acs.py` cannot support the real panel's state
margin; Arm B rejects them rather than silently reporting a false geographic match. This task does
not change Yaza's pipeline or its files.

Only the six demographic columns needed for validation are read from the real file inside the Arm B
analysis. Outputs contain synthetic PUMS respondents, aggregate demographic margins, IPF convergence,
frame counts, and provenance. Individual real rows and survey answers are never written, and there is
no model/provider call or prompt path.

```sh
/usr/local/bin/Rscript analysis/run_arm_b.R \
  --housing /read-only/national-pums/acs_housing_slim.parquet \
  --person /read-only/national-pums/acs_person_slim.parquet \
  --real /read-only/neo_smart_living/survey-760085-2026-03-25-raw-data.csv \
  --output analysis/output/arm_b
```

Run the analysis checks from the repository root:

```sh
/usr/local/bin/Rscript analysis/tests/test_all.R
```

## Arm C verification

`tests/test_arm_c.R` uses invented 256/600-row fixtures and checks the 42-topic prefix join,
anchor stripping, common demographic levels, fixed-seed draws, calibration rounding,
missingness, and emitted caveats. When all three private CSVs are available, it also runs
local alignment and harmonization assertions with source contents and errors suppressed;
otherwise it prints an explicit integration skip. `tests/test_run_all.R` rebuilds the full HTML
twice from invented inputs and requires identical bytes, all three arms, and both Arm C caveats.
Numeric PUMS incomes must be formatted without scientific notation before bracket parsing.
Real validation still requires independently produced Arm C answers and a pre-registered registry;
the test fixtures are not research results.
