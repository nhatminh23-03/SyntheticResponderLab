# Validation analysis

This is the R project for the three validation arms and their reproducible report. Open
`SyntheticResponderLab-analysis.Rproj`, then restore the pinned environment from the repository
root with:

```r
renv::restore(project = "analysis")
```

The initial P4.1 suite uses only base R. Add a package to `renv.lock` in the same change that first
uses it.

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

Run the analysis checks from the repository root:

```sh
/usr/local/bin/Rscript analysis/tests/test_all.R
```
