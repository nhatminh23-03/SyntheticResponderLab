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

Run the analysis checks from the repository root:

```sh
/usr/local/bin/Rscript analysis/tests/test_all.R
```
