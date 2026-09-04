theme_overlap_path <- file.path(repo_root, "analysis", "R", "theme_overlap.R")
source(theme_overlap_path, local = TRUE)

assert_error <- function(expression, pattern) {
  message <- tryCatch(
    {
      force(expression)
      NULL
    },
    error = function(error) conditionMessage(error)
  )
  stopifnot(!is.null(message), grepl(pattern, message, fixed = TRUE))
}

codebook <- data.frame(
  theme_id = c("cost", "space", "aesthetics"),
  label = c("Cost concerns", "Space constraints", "Visual appeal"),
  definition = c(
    "Mentions price, affordability, or value.",
    "Mentions available room, footprint, or placement.",
    "Mentions appearance, style, or visual fit."
  ),
  stringsAsFactors = FALSE
)
real_verbatims <- data.frame(
  response_id = paste0("r", 1:4),
  text = c(
    "OFFLINE_REAL_SENTINEL_1",
    "OFFLINE_REAL_SENTINEL_2",
    "OFFLINE_REAL_SENTINEL_3",
    "OFFLINE_REAL_SENTINEL_4"
  ),
  stringsAsFactors = FALSE
)
synthetic_answers <- data.frame(
  response_id = paste0("s", 1:4),
  text = c(
    "The price would decide it for me.",
    "I would need room near the patio.",
    "It should look intentional.",
    "I like the look if the price works."
  ),
  stringsAsFactors = FALSE
)
judge_models <- c("openai/offline-judge-a", "anthropic/offline-judge-b")

fixture_grid <- theme_overlap_expected_keys(
  judge_models,
  real_verbatims$response_id,
  synthetic_answers$response_id,
  codebook$theme_id
)
fixture_positive <- list(
  "openai/offline-judge-a" = list(
    real = list(r1 = c("cost", "space"), r2 = "cost", r3 = "aesthetics", r4 = character()),
    synthetic = list(s1 = "cost", s2 = "space", s3 = "aesthetics", s4 = c("cost", "aesthetics"))
  ),
  "anthropic/offline-judge-b" = list(
    real = list(r1 = c("cost", "space"), r2 = c("cost", "space"), r3 = "aesthetics", r4 = character()),
    synthetic = list(s1 = "cost", s2 = "space", s3 = c("cost", "aesthetics"), s4 = "cost")
  )
)
fixture_grid$present <- vapply(seq_len(nrow(fixture_grid)), function(index) {
  row <- fixture_grid[index, , drop = FALSE]
  row$theme_id %in% fixture_positive[[row$judge_model]][[row$sample]][[row$response_id]]
}, logical(1L))

judge_calls <- list()
offline_judge_coder <- function(judge_model, sample, responses, codebook) {
  judge_calls[[length(judge_calls) + 1L]] <<- list(
    judge_model = judge_model,
    sample = sample,
    response_ids = responses$response_id,
    texts = responses$text,
    theme_ids = codebook$theme_id
  )
  rows <- fixture_grid[
    fixture_grid$judge_model == judge_model & fixture_grid$sample == sample,
    c("response_id", "theme_id", "present"),
    drop = FALSE
  ]
  rownames(rows) <- NULL
  rows
}

result <- run_theme_overlap(
  real_verbatims,
  synthetic_answers,
  codebook,
  judge_models,
  offline_judge_coder
)

overall <- result$agreement[result$agreement$theme_id == "__overall__", , drop = FALSE]
pooled <- result$overlap_summary[
  result$overlap_summary$judge_model == "__pooled__",
  ,
  drop = FALSE
]
stopifnot(
  inherits(result, "theme_overlap_result"),
  identical(result$judges$model_id, judge_models),
  length(unique(result$judges$model_id)) == 2L,
  result$audit$judge_count == 2L,
  result$audit$judge_invocation_count == 4L,
  result$audit$coding_mode == "independent_judge_coder_fixed_codebook",
  !result$audit$verbatim_text_returned,
  !any(grepl("OFFLINE_REAL_SENTINEL", unlist(result), fixed = TRUE)),
  nrow(result$codings) == 48L,
  identical(
    names(result$codings),
    c("judge_model", "sample", "response_id", "theme_id", "present")
  ),
  nrow(result$theme_prevalence_by_judge) == 6L,
  nrow(result$theme_overlap) == 3L,
  nrow(result$agreement) == 4L,
  overall$rated_units == 24L,
  isTRUE(all.equal(overall$observed_agreement, 21 / 24, tolerance = 1e-12)),
  isTRUE(all.equal(overall$expected_agreement, 25 / 48, tolerance = 1e-12)),
  isTRUE(all.equal(overall$cohens_kappa, 17 / 23, tolerance = 1e-12)),
  isTRUE(all.equal(pooled$weighted_jaccard, 8 / 11, tolerance = 1e-12)),
  pooled$set_jaccard == 1,
  isTRUE(all.equal(pooled$mean_prevalence_similarity, 0.875, tolerance = 1e-12))
)
stopifnot(
  length(judge_calls) == 4L,
  identical(
    vapply(judge_calls, `[[`, character(1L), "judge_model"),
    rep(judge_models, each = 2L)
  ),
  identical(
    vapply(judge_calls, `[[`, character(1L), "sample"),
    rep(THEME_OVERLAP_SAMPLES, times = 2L)
  ),
  identical(judge_calls[[1L]]$texts, real_verbatims$text),
  identical(judge_calls[[2L]]$texts, synthetic_answers$text),
  all(vapply(judge_calls, function(call) {
    identical(call$theme_ids, codebook$theme_id)
  }, logical(1L)))
)

cost_agreement <- result$agreement[result$agreement$theme_id == "cost", , drop = FALSE]
stopifnot(isTRUE(all.equal(cost_agreement$cohens_kappa, 0.75, tolerance = 1e-12)))
per_theme_expected <- data.frame(
  theme_id = codebook$theme_id,
  real_prevalence = c(0.5, 0.375, 0.25),
  synthetic_prevalence = c(0.625, 0.25, 0.375),
  stringsAsFactors = FALSE
)
stopifnot(
  identical(result$theme_overlap$theme_id, per_theme_expected$theme_id),
  isTRUE(all.equal(
    result$theme_overlap$real_prevalence,
    per_theme_expected$real_prevalence,
    tolerance = 1e-12
  )),
  isTRUE(all.equal(
    result$theme_overlap$synthetic_prevalence,
    per_theme_expected$synthetic_prevalence,
    tolerance = 1e-12
  ))
)

printed <- capture.output(print(result))
stopifnot(
  any(grepl(judge_models[[1L]], printed, fixed = TRUE)),
  any(grepl(judge_models[[2L]], printed, fixed = TRUE)),
  any(grepl("Cohen's kappa: 0.739", printed, fixed = TRUE)),
  any(grepl("Jaccard overlap: 0.727", printed, fixed = TRUE))
)

reverse_result <- run_theme_overlap(
  real_verbatims,
  synthetic_answers,
  codebook,
  judge_models,
  function(judge_model, sample, responses, codebook) {
    rows <- offline_judge_coder(judge_model, sample, responses, codebook)
    rows[nrow(rows):1L, , drop = FALSE]
  }
)
stopifnot(
  identical(result$codings, reverse_result$codings),
  identical(result$theme_overlap, reverse_result$theme_overlap),
  identical(result$agreement, reverse_result$agreement)
)

perfect <- cohens_kappa(c(TRUE, FALSE, TRUE, FALSE), c(TRUE, FALSE, TRUE, FALSE))
stopifnot(
  perfect[["observed_agreement"]] == 1,
  perfect[["expected_agreement"]] == 0.5,
  perfect[["cohens_kappa"]] == 1
)
undefined <- cohens_kappa(rep(FALSE, 4L), rep(FALSE, 4L))
stopifnot(
  undefined[["observed_agreement"]] == 1,
  undefined[["expected_agreement"]] == 1,
  is.na(undefined[["cohens_kappa"]])
)
empty_theme_overlap <- theme_overlap_score(c(0, 0), c(0, 0))
stopifnot(
  is.na(empty_theme_overlap[["weighted_jaccard"]]),
  is.na(empty_theme_overlap[["set_jaccard"]]),
  is.na(empty_theme_overlap[["mean_prevalence_similarity"]])
)
padded_theme_overlap <- theme_overlap_score(c(0.5, 0, 0), c(0.25, 0, 0))
stopifnot(
  padded_theme_overlap[["mean_prevalence_similarity"]] == 0.75
)

assert_error(
  validate_theme_judges(c("same/model", "same/model")),
  "must be unique"
)
assert_error(
  validate_theme_judges("only/one-model"),
  "exactly two distinct judge models"
)
assert_error(
  validate_theme_codebook(codebook[, c("theme_id", "label")]),
  "missing required columns: definition"
)
duplicate_codebook <- codebook
duplicate_codebook$theme_id[[2L]] <- duplicate_codebook$theme_id[[1L]]
assert_error(validate_theme_codebook(duplicate_codebook), "theme_id values must be unique")
assert_error(
  validate_theme_texts(real_verbatims[FALSE, ], "response_id", "text", "Real verbatims"),
  "must contain at least one response"
)
assert_error(
  validate_theme_texts(real_verbatims, "response_id", "response_id", "Real verbatims"),
  "ID and text columns must be different"
)
blank_real <- real_verbatims
blank_real$text[[1L]] <- ""
assert_error(
  validate_theme_texts(blank_real, "response_id", "text", "Real verbatims"),
  "text must be present and non-blank"
)
assert_error(cohens_kappa(c(TRUE, FALSE), TRUE), "equal length")
assert_error(cohens_kappa(c(TRUE, NA), c(TRUE, FALSE)), "must be complete")
assert_error(theme_overlap_score(c(0.5), c(1.1)), "bounded by zero and one")
assert_error(
  run_theme_overlap(real_verbatims, synthetic_answers, codebook, judge_models, NULL),
  "judge_coder must be a function"
)
assert_error(
  run_theme_overlap(
    real_verbatims,
    synthetic_answers,
    codebook,
    judge_models,
    function(...) stop("offline judge failure")
  ),
  "offline judge failure"
)

validate_fixture_codings <- function(codings) {
  validate_theme_codings(
    codings,
    judge_models,
    real_verbatims$response_id,
    synthetic_answers$response_id,
    codebook$theme_id
  )
}

duplicate_codings <- rbind(fixture_grid, fixture_grid[1L, ])
assert_error(
  validate_fixture_codings(duplicate_codings),
  "duplicates found"
)
missing_codings <- fixture_grid[-1L, ]
assert_error(
  validate_fixture_codings(missing_codings),
  "found 1 missing and 0 unexpected decisions"
)
bad_theme_codings <- fixture_grid
bad_theme_codings$theme_id[[1L]] <- "invented_after_reading_answers"
assert_error(
  validate_fixture_codings(bad_theme_codings),
  "outside the fixed codebook"
)
bad_judge_codings <- fixture_grid
bad_judge_codings$judge_model[[1L]] <- "third/unregistered-model"
assert_error(
  validate_fixture_codings(bad_judge_codings),
  "outside the two registered judges"
)
bad_sample_codings <- fixture_grid
bad_sample_codings$sample[[1L]] <- "combined"
assert_error(
  validate_fixture_codings(bad_sample_codings),
  "unsupported sample values"
)
bad_response_codings <- fixture_grid
bad_response_codings$response_id[[1L]] <- "unknown-real-response"
assert_error(
  validate_fixture_codings(bad_response_codings),
  "outside their declared sample"
)
bad_presence_codings <- fixture_grid
bad_presence_codings$present <- as.integer(bad_presence_codings$present)
bad_presence_codings$present[[1L]] <- 2L
assert_error(
  validate_fixture_codings(bad_presence_codings),
  "TRUE/FALSE or 1/0"
)

all_absent_coder <- function(judge_model, sample, responses, codebook) {
  rows <- merge(
    data.frame(response_id = responses$response_id, stringsAsFactors = FALSE),
    data.frame(theme_id = codebook$theme_id, stringsAsFactors = FALSE),
    all = TRUE
  )
  rows$present <- FALSE
  rows
}
absent_result <- run_theme_overlap(
  real_verbatims,
  synthetic_answers,
  codebook,
  judge_models,
  all_absent_coder
)
stopifnot(
  all(is.na(absent_result$agreement$cohens_kappa)),
  all(absent_result$agreement$status == "undefined_no_expected_disagreement"),
  all(is.na(absent_result$overlap_summary$weighted_jaccard)),
  all(is.na(absent_result$overlap_summary$set_jaccard)),
  all(is.na(absent_result$overlap_summary$mean_prevalence_similarity)),
  any(grepl(
    "Jaccard overlap: undefined (no observed themes)",
    capture.output(print(absent_result)),
    fixed = TRUE
  )),
  any(grepl("undefined (no expected disagreement)", capture.output(print(absent_result)), fixed = TRUE))
)

cat("test_theme_overlap.R: PASS\n")
