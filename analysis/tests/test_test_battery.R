test_battery_path <- file.path(repo_root, "analysis", "R", "test_battery.R")
runner_path <- file.path(repo_root, "analysis", "run_test_battery.R")
source(test_battery_path, local = TRUE)
source(runner_path, local = TRUE)

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

respondent_n <- 120L
base_continuous <- rep(seq(-1, 1, length.out = respondent_n / 2L), 2L)
real_data <- data.frame(
  real_id = sprintf("real_%03d", seq_len(respondent_n)),
  continuous_item = base_continuous,
  binary_item = rep(c("No", "Yes"), each = respondent_n / 2L),
  categorical_item = rep(c("A", "B", "C"), each = respondent_n / 3L),
  private_answer_sentinel = "REAL_ANSWER_SENTINEL",
  stringsAsFactors = FALSE
)
synthetic_data <- data.frame(
  synthetic_id = sprintf("synthetic_%03d", seq_len(respondent_n)),
  continuous_item = base_continuous + 0.05,
  binary_item = c(rep("No", 57L), rep("Yes", 63L)),
  categorical_item = c(rep("A", 42L), rep("B", 38L), rep("C", 40L)),
  stringsAsFactors = FALSE
)
registry <- data.frame(
  question_id = c("continuous_item", "binary_item", "categorical_item"),
  question_type = c("continuous", "binary", "categorical"),
  equivalence_margin = c(0.25, 0.15, 0.15),
  positive_level = c("", "Yes", ""),
  stringsAsFactors = FALSE
)

validated_registry <- validate_question_registry(registry)
stopifnot(
  identical(validated_registry$question_id, registry$question_id),
  is.na(validated_registry$positive_level[[1L]]),
  validated_registry$positive_level[[2L]] == "Yes"
)

small_sample_g <- hedges_g(c(0, 2), c(1, 4), 0.95)
small_sample_df <- 2
small_sample_correction <- 1 - 3 / (4 * small_sample_df - 1)
small_sample_pooled_variance <- (stats::var(c(0, 2)) + stats::var(c(1, 4))) / 2
small_sample_d <- (mean(c(0, 2)) - mean(c(1, 4))) / sqrt(small_sample_pooled_variance)
small_sample_estimate <- small_sample_correction * small_sample_d
small_sample_standard_error <- sqrt(
  small_sample_correction^2 * (2 + 2) / (2 * 2) +
    small_sample_estimate^2 / (2 * small_sample_df)
)
small_sample_critical <- stats::qnorm(0.975)
stopifnot(
  isTRUE(all.equal(unname(small_sample_g[["estimate"]]), small_sample_estimate, tolerance = 1e-12)),
  isTRUE(all.equal(
    unname(small_sample_g[["confidence_lower"]]),
    small_sample_estimate - small_sample_critical * small_sample_standard_error,
    tolerance = 1e-12
  )),
  isTRUE(all.equal(
    unname(small_sample_g[["confidence_upper"]]),
    small_sample_estimate + small_sample_critical * small_sample_standard_error,
    tolerance = 1e-12
  ))
)

set.seed(88L)
seed_before <- .Random.seed
result <- run_test_battery(
  real_data,
  synthetic_data,
  registry,
  "real_id",
  "synthetic_id",
  bootstrap_replicates = 200L,
  seed = 41L
)
stopifnot(
  identical(.Random.seed, seed_before),
  identical(result$results$question_id, registry$question_id),
  identical(
    result$results$test,
    c(
      "Welch two-sample t-test",
      "two-sample Wald z-test",
      "Pearson chi-square test of homogeneity"
    )
  ),
  identical(
    result$results$effect_size,
    c("mean_difference_real_minus_synthetic", "risk_difference_real_minus_synthetic", "cramers_v")
  ),
  all(is.finite(result$results$effect_estimate)),
  all(is.finite(result$results$confidence_lower)),
  all(is.finite(result$results$confidence_upper)),
  all(result$results$real_n == respondent_n),
  all(result$results$synthetic_n == respondent_n),
  all(result$results$confidence_level == 0.95),
  all(result$results$tost_confidence_level == 0.90),
  all(result$results$equivalent),
  nrow(result$equivalence) == 5L,
  all(is.finite(result$equivalence$effect_estimate)),
  all(is.finite(result$equivalence$confidence_lower)),
  all(is.finite(result$equivalence$confidence_upper)),
  all(result$equivalence$equivalence_margin > 0),
  all(result$equivalence$confidence_level == 0.90),
  all(result$equivalence$equivalent)
)

continuous_row <- result$results[result$results$question_id == "continuous_item", , drop = FALSE]
expected_t_test <- stats::t.test(real_data$continuous_item, synthetic_data$continuous_item)
stopifnot(
  isTRUE(all.equal(continuous_row$effect_estimate, -0.05, tolerance = 1e-12)),
  isTRUE(all.equal(continuous_row$statistic, unname(expected_t_test$statistic), tolerance = 1e-12)),
  isTRUE(all.equal(continuous_row$p_value, expected_t_test$p.value, tolerance = 1e-12)),
  isTRUE(all.equal(continuous_row$confidence_lower, expected_t_test$conf.int[[1L]], tolerance = 1e-12)),
  isTRUE(all.equal(continuous_row$confidence_upper, expected_t_test$conf.int[[2L]], tolerance = 1e-12)),
  continuous_row$standardized_effect_size == "hedges_g",
  all(is.finite(unlist(continuous_row[c(
    "standardized_effect_estimate",
    "standardized_confidence_lower",
    "standardized_confidence_upper"
  )])))
)

binary_row <- result$results[result$results$question_id == "binary_item", , drop = FALSE]
binary_real_proportion <- mean(real_data$binary_item == "Yes")
binary_synthetic_proportion <- mean(synthetic_data$binary_item == "Yes")
binary_standard_error <- sqrt(
  binary_real_proportion * (1 - binary_real_proportion) / respondent_n +
    binary_synthetic_proportion * (1 - binary_synthetic_proportion) / respondent_n
)
stopifnot(
  isTRUE(all.equal(
    binary_row$effect_estimate,
    binary_real_proportion - binary_synthetic_proportion,
    tolerance = 1e-12
  )),
  isTRUE(all.equal(
    binary_row$statistic,
    binary_row$effect_estimate / binary_standard_error,
    tolerance = 1e-12
  )),
  grepl("approximation check passed", binary_row$assumption_note, fixed = TRUE)
)

categorical_row <- result$results[result$results$question_id == "categorical_item", , drop = FALSE]
categorical_table <- rbind(c(40, 40, 40), c(42, 38, 40))
expected_chi_square <- suppressWarnings(stats::chisq.test(categorical_table, correct = FALSE))
expected_cramers_v <- sqrt(unname(expected_chi_square$statistic) / sum(categorical_table))
stopifnot(
  isTRUE(all.equal(categorical_row$statistic, unname(expected_chi_square$statistic), tolerance = 1e-12)),
  isTRUE(all.equal(categorical_row$p_value, expected_chi_square$p.value, tolerance = 1e-12)),
  isTRUE(all.equal(categorical_row$effect_estimate, expected_cramers_v, tolerance = 1e-12)),
  categorical_row$confidence_lower >= 0,
  categorical_row$confidence_upper <= 1,
  identical(
    result$equivalence$level[result$equivalence$question_id == "categorical_item"],
    c("A", "B", "C")
  )
)

categorical_only_registry <- registry[registry$question_id == "categorical_item", , drop = FALSE]
identical_categorical <- run_test_battery(
  real_data,
  transform(synthetic_data, categorical_item = real_data$categorical_item),
  categorical_only_registry,
  "real_id",
  "synthetic_id",
  bootstrap_replicates = 500L,
  seed = 19L
)
identical_categorical_row <- identical_categorical$results[1L, , drop = FALSE]
stopifnot(
  identical_categorical_row$effect_estimate == 0,
  identical_categorical_row$p_value == 1,
  identical_categorical_row$confidence_lower == 0,
  identical_categorical_row$confidence_upper > 0,
  identical_categorical_row$confidence_lower <= identical_categorical_row$effect_estimate,
  identical_categorical_row$confidence_upper >= identical_categorical_row$effect_estimate
)

repeat_result <- run_test_battery(
  real_data,
  synthetic_data,
  registry,
  "real_id",
  "synthetic_id",
  bootstrap_replicates = 200L,
  seed = 41L
)
stopifnot(identical(result, repeat_result))

different_continuous <- synthetic_data
different_continuous$continuous_item <- different_continuous$continuous_item + 1
continuous_only_registry <- registry[registry$question_id == "continuous_item", , drop = FALSE]
non_equivalent <- run_test_battery(
  real_data,
  different_continuous,
  continuous_only_registry,
  "real_id",
  "synthetic_id",
  bootstrap_replicates = 100L
)
stopifnot(
  !non_equivalent$results$equivalent,
  !non_equivalent$equivalence$equivalent,
  non_equivalent$results$tost_p_value >= TEST_BATTERY_ALPHA
)

small_real <- data.frame(
  id = paste0("r", 1:10),
  category = c(rep("common", 9), "rare"),
  stringsAsFactors = FALSE
)
small_synthetic <- data.frame(
  id = paste0("s", 1:10),
  category = c(rep("common", 8), rep("rare", 2)),
  stringsAsFactors = FALSE
)
small_registry <- data.frame(
  question_id = "category",
  question_type = "categorical",
  equivalence_margin = 0.7,
  stringsAsFactors = FALSE
)
small_result <- run_test_battery(
  small_real,
  small_synthetic,
  small_registry,
  "id",
  "id",
  bootstrap_replicates = 100L
)
stopifnot(grepl("approximation is weak", small_result$results$assumption_note, fixed = TRUE))

assert_error(
  validate_question_registry(registry[, names(registry) != "equivalence_margin"]),
  "missing required columns: equivalence_margin"
)
assert_error(
  validate_question_registry(registry[FALSE, ]),
  "must contain at least one analyzable question"
)
duplicate_registry <- registry
duplicate_registry$question_id[[2L]] <- duplicate_registry$question_id[[1L]]
assert_error(validate_question_registry(duplicate_registry), "must be present and unique")
ambiguous_registry <- registry
ambiguous_registry$question_id_copy <- ambiguous_registry$question_id
names(ambiguous_registry)[[ncol(ambiguous_registry)]] <- "question_id"
assert_error(validate_question_registry(ambiguous_registry), "ambiguous duplicate required columns")
unsupported_registry <- registry
unsupported_registry$question_type[[1L]] <- "open_text"
assert_error(validate_question_registry(unsupported_registry), "unsupported question types")
missing_positive <- registry
missing_positive$positive_level[[2L]] <- ""
assert_error(validate_question_registry(missing_positive), "must declare a positive_level")
invalid_margin <- registry
invalid_margin$equivalence_margin[[1L]] <- 0
assert_error(validate_question_registry(invalid_margin), "finite, positive")
invalid_proportion_margin <- registry
invalid_proportion_margin$equivalence_margin[[2L]] <- 1
assert_error(validate_question_registry(invalid_proportion_margin), "strictly between 0 and 1")

assert_error(
  run_test_battery(
    real_data[, names(real_data) != "continuous_item"],
    synthetic_data,
    registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "missing required columns: continuous_item"
)
duplicate_ids <- real_data
duplicate_ids$real_id[[2L]] <- duplicate_ids$real_id[[1L]]
assert_error(
  run_test_battery(
    duplicate_ids,
    synthetic_data,
    registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "respondent IDs must be present and unique"
)
ambiguous_questions <- real_data
ambiguous_questions$continuous_item_copy <- ambiguous_questions$continuous_item + 100
names(ambiguous_questions)[[ncol(ambiguous_questions)]] <- "continuous_item"
assert_error(
  run_test_battery(
    ambiguous_questions,
    synthetic_data,
    continuous_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "ambiguous duplicate required columns: continuous_item"
)
assert_error(
  run_test_battery(
    real_data,
    synthetic_data,
    continuous_only_registry,
    "continuous_item",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "ID column must not also be a registered question column"
)
assert_error(
  run_test_battery(
    real_data[1L, ],
    synthetic_data,
    continuous_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "at least two respondents"
)
invalid_continuous <- real_data
invalid_continuous$continuous_item[[1L]] <- NA_real_
assert_error(
  run_test_battery(
    invalid_continuous,
    synthetic_data,
    continuous_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "responses must be complete, finite numbers"
)
constant_real <- real_data
constant_synthetic <- synthetic_data
constant_real$continuous_item <- 1
constant_synthetic$continuous_item <- 1
assert_error(
  run_test_battery(
    constant_real,
    constant_synthetic,
    continuous_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "positive Welch standard error"
)

binary_only_registry <- registry[registry$question_id == "binary_item", , drop = FALSE]
three_level_binary <- synthetic_data
three_level_binary$binary_item[[1L]] <- "Maybe"
assert_error(
  run_test_battery(
    real_data,
    three_level_binary,
    binary_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "exactly two observed response levels"
)
unobserved_positive <- binary_only_registry
unobserved_positive$positive_level <- "Maybe"
assert_error(
  run_test_battery(
    real_data,
    synthetic_data,
    unobserved_positive,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "is not observed"
)
separated_real <- real_data
separated_synthetic <- synthetic_data
separated_real$binary_item <- "Yes"
separated_synthetic$binary_item <- "No"
assert_error(
  run_test_battery(
    separated_real,
    separated_synthetic,
    binary_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "finite, positive unpooled standard error"
)

one_level_real <- real_data
one_level_synthetic <- synthetic_data
one_level_real$categorical_item <- "A"
one_level_synthetic$categorical_item <- "A"
assert_error(
  run_test_battery(
    one_level_real,
    one_level_synthetic,
    categorical_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "at least two observed response levels"
)
blank_categorical <- real_data
blank_categorical$categorical_item[[1L]] <- ""
assert_error(
  run_test_battery(
    blank_categorical,
    synthetic_data,
    categorical_only_registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L
  ),
  "complete, non-blank categories"
)
assert_error(
  run_test_battery(
    real_data,
    synthetic_data,
    registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 99L
  ),
  "integer of at least 100"
)
assert_error(
  run_test_battery(
    real_data,
    synthetic_data,
    registry,
    "real_id",
    "synthetic_id",
    alpha = 0.5,
    bootstrap_replicates = 100L
  ),
  "strictly between 0 and 0.5"
)
assert_error(
  run_test_battery(
    real_data,
    synthetic_data,
    registry,
    "real_id",
    "synthetic_id",
    confidence_level = 1,
    bootstrap_replicates = 100L
  ),
  "strictly between 0 and 1"
)
assert_error(
  run_test_battery(
    real_data,
    synthetic_data,
    registry,
    "real_id",
    "synthetic_id",
    bootstrap_replicates = 100L,
    seed = NA_integer_
  ),
  "must be one integer"
)

if (exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)) {
  rm(".Random.seed", envir = .GlobalEnv)
}
invisible(bootstrap_cramers_v(
  real_data$categorical_item,
  synthetic_data$categorical_item,
  c("A", "B", "C"),
  100L,
  12L,
  0.95
))
stopifnot(!exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE))

parsed <- parse_test_battery_arguments(c(
  "--real", "real.csv",
  "--synthetic", "synthetic.csv",
  "--registry", "registry.csv",
  "--real-id", "real_id",
  "--synthetic-id", "synthetic_id",
  "--output", "out"
))
stopifnot(
  parsed$real == "real.csv",
  parsed$synthetic == "synthetic.csv",
  parsed$registry == "registry.csv",
  parsed[["real-id"]] == "real_id",
  parsed[["synthetic-id"]] == "synthetic_id",
  parsed$output == "out"
)
assert_error(parse_test_battery_arguments(c("--real", "only.csv")), "Missing required arguments")
assert_error(
  parse_test_battery_arguments(c(
    "--real", "r", "--synthetic", "s", "--registry", "q",
    "--real-id", "id", "--synthetic-id", "id", "--margin", "0.2"
  )),
  "Unknown arguments: margin"
)
assert_error(
  test_battery_main(c(
    "--real", "missing-real", "--synthetic", "missing-synthetic",
    "--registry", "missing-registry", "--real-id", "id", "--synthetic-id", "id"
  )),
  "input was not found"
)

real_path <- tempfile(fileext = ".csv")
synthetic_path <- tempfile(fileext = ".csv")
registry_path <- tempfile(fileext = ".csv")
output_directory <- tempfile(pattern = "test-battery-")
utils::write.csv(real_data, real_path, row.names = FALSE)
utils::write.csv(synthetic_data, synthetic_path, row.names = FALSE)
utils::write.csv(registry, registry_path, row.names = FALSE)
main_result <- NULL
invisible(capture.output(main_result <- test_battery_main(c(
  "--real", real_path,
  "--synthetic", synthetic_path,
  "--registry", registry_path,
  "--real-id", "real_id",
  "--synthetic-id", "synthetic_id",
  "--output", output_directory
))))
expected_outputs <- c(
  "test_results.csv",
  "tost_details.csv",
  "registered_questions.csv",
  "provenance.txt"
)
stopifnot(
  all(file.exists(file.path(output_directory, expected_outputs))),
  nrow(main_result$results) == 3L
)
written_results <- utils::read.csv(
  file.path(output_directory, "test_results.csv"),
  stringsAsFactors = FALSE
)
written_tost <- utils::read.csv(
  file.path(output_directory, "tost_details.csv"),
  stringsAsFactors = FALSE
)
stopifnot(
  all(c("real_n", "synthetic_n", "effect_estimate", "confidence_lower", "confidence_upper", "p_value") %in%
    names(written_results)),
  all(c("effect_estimate", "confidence_lower", "confidence_upper", "p_value") %in%
    names(written_tost)),
  !"private_answer_sentinel" %in% names(written_results),
  !"private_answer_sentinel" %in% names(written_tost)
)
output_contents <- unlist(lapply(
  list.files(output_directory, full.names = TRUE),
  readLines,
  warn = FALSE
))
provenance <- readLines(file.path(output_directory, "provenance.txt"), warn = FALSE)
stopifnot(
  !any(grepl("REAL_ANSWER_SENTINEL", output_contents, fixed = TRUE)),
  any(grepl("Registry MD5 at analysis time", provenance, fixed = TRUE)),
  any(grepl("respondent-level real answers are not written", provenance, fixed = TRUE)),
  any(grepl("no model, prompt, or provider call", provenance, fixed = TRUE))
)
unlink(c(real_path, synthetic_path, registry_path, output_directory), recursive = TRUE)

cat("test_test_battery.R: PASS\n")
