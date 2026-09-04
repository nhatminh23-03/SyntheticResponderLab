screen_counts_path <- file.path(repo_root, "analysis", "screen_counts.R")
arm_b_path <- file.path(repo_root, "analysis", "R", "arm_b.R")
runner_path <- file.path(repo_root, "analysis", "run_arm_b.R")
source(screen_counts_path, local = TRUE)
source(arm_b_path, local = TRUE)
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

age_values <- c(22, 30, 40, 50, 60, 70)
income_values <- c(10000, 30000, 60000, 85000, 120000, 220000)
state_values <- c(6, 36, 39, 48)
donors <- expand.grid(
  age = age_values,
  income = income_values,
  sex = c(1, 2),
  state = state_values,
  replicate = seq_len(12L),
  KEEP.OUT.ATTRS = FALSE,
  stringsAsFactors = FALSE
)
donor_n <- nrow(donors)
housing <- data.frame(
  SERIALNO = sprintf("B%04d", seq_len(donor_n)),
  ST = donors$state,
  WGTP = 1 + (seq_len(donor_n) * 7L) %% 23L,
  TEN = 1,
  HINCP = donors$income,
  ADJINC = 1000000,
  stringsAsFactors = FALSE
)
person <- data.frame(
  SERIALNO = housing$SERIALNO,
  ST = donors$state,
  RELSHIPP = 20,
  AGEP = donors$age,
  SEX = donors$sex,
  stringsAsFactors = FALSE
)

respondent_n <- 600L
real_age <- rep(age_values, length.out = respondent_n)
real_income <- rep(ARM_B_INCOME_LEVELS, each = 100L)
real_gender <- rep(c("Female", "Male"), each = 300L)
real_state <- rep(c("California", "New York", "Ohio", "Texas"), times = c(40, 180, 120, 260))
real_data <- data.frame(
  "Response ID" = c(NA, seq_len(respondent_n)),
  Status = c(NA_character_, rep("Completed", respondent_n)),
  Gender = c("", real_gender),
  Age = c(NA, real_age),
  "Household Income" = c("", real_income),
  State = c("", real_state),
  "Q32: real answer sentinel" = c("", rep("REAL_ANSWER_SENTINEL", respondent_n)),
  check.names = FALSE,
  stringsAsFactors = FALSE
)

stopifnot(
  identical(
    arm_b_age_band(c(18, 24, 25, 34, 35, 44, 45, 54, 55, 64, 65)),
    c("18-24", "18-24", "25-34", "25-34", "35-44", "35-44",
      "45-54", "45-54", "55-64", "55-64", "65+")
  ),
  identical(arm_b_income_band(income_values), ARM_B_INCOME_LEVELS),
  identical(arm_b_state_name(c(6, 48, NA, 99)), c("California", "Texas", NA, NA))
)

real <- harmonize_arm_b_real(real_data)
stopifnot(
  nrow(real) == respondent_n,
  identical(names(real), c("age", "age_band", "gender", "income_band", "state")),
  sum(real$state == "California") == 40L,
  setequal(unique(real$income_band), ARM_B_INCOME_LEVELS)
)
assert_error(harmonize_arm_b_real(real_data[1:10, ]), "Expected exactly 600 completed real respondents")
bad_real <- real_data
bad_real[["Response ID"]][[3L]] <- bad_real[["Response ID"]][[2L]]
assert_error(harmonize_arm_b_real(bad_real), "IDs must be present and unique")
bad_real <- real_data
bad_real$Age[[2L]] <- 17
assert_error(harmonize_arm_b_real(bad_real), "at least 18")
bad_real <- real_data
bad_real$Gender[[2L]] <- "Other"
assert_error(harmonize_arm_b_real(bad_real), "levels Female or Male")
bad_real <- real_data
bad_real[["Household Income"]][[2L]] <- "Unknown"
assert_error(harmonize_arm_b_real(bad_real), "income contains unsupported levels")
bad_real <- real_data
bad_real$State[[2L]] <- "Puerto Rico"
assert_error(harmonize_arm_b_real(bad_real), "state contains unsupported levels")
assert_error(
  harmonize_arm_b_real(real_data[, names(real_data) != "State"]),
  "missing required columns: State"
)

pums <- build_arm_b_pums_frame(housing, person)
stopifnot(
  nrow(pums$frame) == donor_n,
  identical(as.integer(pums$audit$records), rep(donor_n, 4L)),
  all(pums$frame$base_weight > 0),
  setequal(unique(pums$frame$age_band), ARM_B_AGE_LEVELS),
  setequal(unique(pums$frame$income_band), ARM_B_INCOME_LEVELS),
  setequal(unique(pums$frame$state), c("California", "New York", "Ohio", "Texas"))
)

filtered_housing <- housing
filtered_person <- person
filtered_housing$TEN[[1L]] <- NA
filtered_housing$WGTP[[2L]] <- 0
filtered_person$AGEP[[3L]] <- 17
filtered <- build_arm_b_pums_frame(filtered_housing, filtered_person)
stopifnot(
  identical(as.integer(filtered$audit$records), c(donor_n, donor_n - 1L, donor_n - 1L, donor_n - 3L)),
  nrow(filtered$frame) == donor_n - 3L
)
assert_error(
  build_arm_b_pums_frame(housing[, names(housing) != "ADJINC"], person),
  "missing required columns: ADJINC"
)
duplicate_housing <- rbind(housing, housing[1L, ])
assert_error(build_arm_b_pums_frame(duplicate_housing, person), "housing PUMS SERIALNO must be unique")
duplicate_person <- rbind(person, person[1L, ])
assert_error(build_arm_b_pums_frame(housing, duplicate_person), "householder SERIALNO must be unique")
wrong_state_person <- person
wrong_state_person$ST[[1L]] <- 48
assert_error(build_arm_b_pums_frame(housing, wrong_state_person), "state codes must be present and agree")
empty_housing <- housing
empty_housing$TEN <- NA
assert_error(build_arm_b_pums_frame(empty_housing, person), "has no eligible adult householders")
blank_id_housing <- housing
blank_id_person <- person
blank_id_housing$SERIALNO[[1L]] <- ""
blank_id_person$SERIALNO[[1L]] <- ""
assert_error(build_arm_b_pums_frame(blank_id_housing, blank_id_person), "donor IDs must be present and unique")

targets <- arm_b_targets(real)
stopifnot(
  identical(names(targets), c("age_band", "gender", "income_band", "state")),
  all(abs(vapply(targets, sum, numeric(1L)) - 1) < 1e-12),
  targets$state[["California"]] == 40 / 600,
  targets$state[["Alaska"]] == 0
)

fitted_one <- fit_arm_b_ipf(pums$frame, targets)
fitted_two <- fit_arm_b_ipf(pums$frame, targets)
stopifnot(
  identical(fitted_one$weights, fitted_two$weights),
  fitted_one$iterations >= 1L,
  fitted_one$max_error <= ARM_B_IPF_TOLERANCE,
  tail(fitted_one$convergence$max_absolute_margin_error, 1L) <= ARM_B_IPF_TOLERANCE,
  all(fitted_one$weights[pums$frame$state %in% c("California", "New York", "Ohio", "Texas")] > 0)
)

simple_frame <- data.frame(
  first = c("A", "A", "B", "B"),
  second = c("X", "Y", "X", "Y"),
  base_weight = c(10, 1, 1, 1),
  stringsAsFactors = FALSE
)
simple_targets <- list(
  first = c(A = 0.75, B = 0.25),
  second = c(X = 0.25, Y = 0.75)
)
simple_fit <- fit_arm_b_ipf(simple_frame, simple_targets)
for (characteristic in names(simple_targets)) {
  fitted_margin <- tapply(simple_fit$weights, simple_frame[[characteristic]], sum)
  fitted_margin <- fitted_margin / sum(fitted_margin)
  stopifnot(max(abs(fitted_margin[names(simple_targets[[characteristic]])] -
    simple_targets[[characteristic]])) <= ARM_B_IPF_TOLERANCE)
}
zero_target <- simple_targets
zero_target$first <- c(A = 1, B = 0)
zero_fit <- fit_arm_b_ipf(simple_frame, zero_target)
stopifnot(all(zero_fit$weights[simple_frame$first == "B"] == 0))

assert_error(fit_arm_b_ipf(simple_frame, list()), "named, non-empty list")
assert_error(
  fit_arm_b_ipf(simple_frame, list(missing = c(A = 1))),
  "missing required columns: missing"
)
assert_error(
  fit_arm_b_ipf(simple_frame, simple_targets, base_weights = c(1, 1)),
  "one value per PUMS row"
)
invalid_targets <- simple_targets
invalid_targets$first <- c(A = 1, A = 0)
assert_error(fit_arm_b_ipf(simple_frame, invalid_targets), "target margin first is invalid")
unsupported_targets <- simple_targets
unsupported_targets$first <- c(A = 0.5, B = 0.25, C = 0.25)
assert_error(fit_arm_b_ipf(simple_frame, unsupported_targets), "lacks support for observed first levels: C")
unknown_frame <- simple_frame
unknown_frame$first[[1L]] <- "C"
assert_error(fit_arm_b_ipf(unknown_frame, simple_targets), "contains unsupported first levels")
assert_error(fit_arm_b_ipf(simple_frame, simple_targets, tolerance = 0), "tolerance must be")
assert_error(fit_arm_b_ipf(simple_frame, simple_targets, max_iterations = 0), "positive integer")
assert_error(
  fit_arm_b_ipf(simple_frame, simple_targets, tolerance = 1e-16, max_iterations = 1L),
  "did not converge within 1 iterations"
)
incompatible_frame <- simple_frame[c(1L, 4L), ]
incompatible_targets <- list(first = c(A = 1, B = 0), second = c(X = 0, Y = 1))
assert_error(
  fit_arm_b_ipf(incompatible_frame, incompatible_targets),
  "lost support for second levels during fitting: Y"
)

draw_one <- draw_arm_b(
  pums$frame, fitted_one$weights, targets, n = respondent_n, seed = ARM_B_SEED
)
draw_two <- draw_arm_b(
  pums$frame, fitted_one$weights, targets, n = respondent_n, seed = ARM_B_SEED
)
stopifnot(
  identical(draw_one, draw_two),
  nrow(draw_one) == respondent_n,
  !anyDuplicated(draw_one$donor_id)
)
for (characteristic in names(targets)) {
  drawn_counts <- as.integer(table(factor(
    draw_one[[characteristic]], levels = names(targets[[characteristic]])
  )))
  stopifnot(identical(drawn_counts, as.integer(round(respondent_n * targets[[characteristic]]))))
}
assert_error(draw_arm_b(pums$frame, fitted_one$weights, targets, n = 0), "positive integer")
assert_error(
  draw_arm_b(pums$frame, c(fitted_one$weights[-1L], NA), targets, n = 1),
  "finite, non-negative"
)
assert_error(
  draw_arm_b(pums$frame, rep(0, donor_n), targets, n = 1),
  "only 0 positive-weight records"
)
assert_error(
  draw_arm_b(pums$frame, fitted_one$weights, targets, n = 599L),
  "does not produce integer counts"
)
assert_error(harmonize_arm_b_synthetic(draw_one[FALSE, ]), "unique PUMS donors")
duplicate_draw <- draw_one
duplicate_draw$donor_id[[2L]] <- duplicate_draw$donor_id[[1L]]
assert_error(harmonize_arm_b_synthetic(duplicate_draw), "unique PUMS donors")

result_one <- run_arm_b(housing, person, real_data)
result_two <- run_arm_b(housing, person, real_data)
stopifnot(
  result_one$seed == ARM_B_SEED,
  result_one$draw_n == ARM_B_DRAW_N,
  identical(result_one$synthetic, result_two$synthetic),
  nrow(result_one$synthetic) == respondent_n,
  !anyDuplicated(result_one$synthetic$synthetic_id),
  identical(result_one$match_characteristics, c("age_band", "gender", "income_band", "state")),
  max(abs(result_one$margin_audit$raked_difference_percentage_points)) <=
    100 * ARM_B_IPF_TOLERANCE,
  all(result_one$margin_audit$selected_n == result_one$margin_audit$target_n),
  all(abs(result_one$margin_audit$selected_difference_percentage_points) < 1e-12)
)
audit_groups <- split(result_one$margin_audit, result_one$margin_audit$characteristic)
stopifnot(
  all(vapply(audit_groups, function(frame) sum(frame$target_n), integer(1L)) == respondent_n),
  all(vapply(audit_groups, function(frame) sum(frame$selected_n), integer(1L)) == respondent_n),
  all(abs(vapply(audit_groups, function(frame) sum(frame$raked_proportion), numeric(1L)) - 1) < 1e-12),
  all(abs(vapply(audit_groups, function(frame) sum(frame$selected_proportion), numeric(1L)) - 1) < 1e-12)
)

california_only_housing <- housing[housing$ST == 6, , drop = FALSE]
california_only_person <- person[person$ST == 6, , drop = FALSE]
assert_error(
  run_arm_b(california_only_housing, california_only_person, real_data),
  "PUMS frame lacks support for observed state levels"
)

parsed <- parse_arm_b_arguments(c(
  "--housing", "housing.parquet",
  "--person", "person.parquet",
  "--real", "real.csv",
  "--output", "out"
))
stopifnot(
  parsed$housing == "housing.parquet",
  parsed$person == "person.parquet",
  parsed$real == "real.csv",
  parsed$output == "out"
)
default_parsed <- parse_arm_b_arguments(c(
  "--housing", "housing.parquet", "--person", "person.parquet", "--real", "real.csv"
))
stopifnot(default_parsed$output == file.path("analysis", "output", "arm_b"))
assert_error(parse_arm_b_arguments(c("--housing", "only.parquet")), "Missing required arguments")
assert_error(parse_arm_b_arguments(c("housing", "file")), arm_b_usage())
assert_error(
  parse_arm_b_arguments(c("--housing", "h", "--person", "p", "--real", "r", "--seed", "1")),
  "Unknown arguments: seed"
)
assert_error(
  parse_arm_b_arguments(c(
    "--housing", "one", "--housing", "two", "--person", "p", "--real", "r"
  )),
  "was supplied more than once"
)
assert_error(
  arm_b_main(c("--housing", "missing-housing", "--person", "missing-person", "--real", "missing-real")),
  "Arm B input was not found"
)

real_path <- tempfile(fileext = ".csv")
utils::write.csv(real_data, real_path, row.names = FALSE)
read_real <- read_arm_b_real_demographics(real_path)
stopifnot(
  identical(
    names(read_real),
    c("Response ID", "Status", "Gender", "Age", "Household Income", "State")
  ),
  !"Q32: real answer sentinel" %in% names(read_real)
)
bad_real_path <- tempfile(fileext = ".csv")
utils::write.csv(real_data[, names(real_data) != "State"], bad_real_path, row.names = FALSE)
assert_error(read_arm_b_real_demographics(bad_real_path), "missing required columns: State")

output_directory <- tempfile(pattern = "arm-b-")
write_arm_b_results(
  result_one,
  output_directory,
  list(housing = "housing-source", person = "person-source", real = "real-source")
)
expected_outputs <- c(
  "synthetic_respondents.csv",
  "margin_audit.csv",
  "ipf_convergence.csv",
  "frame_audit.csv",
  "provenance.txt"
)
stopifnot(all(file.exists(file.path(output_directory, expected_outputs))))
written_synthetic <- utils::read.csv(
  file.path(output_directory, "synthetic_respondents.csv"),
  stringsAsFactors = FALSE
)
written_audit <- utils::read.csv(file.path(output_directory, "margin_audit.csv"), stringsAsFactors = FALSE)
stopifnot(
  nrow(written_synthetic) == respondent_n,
  !"donor_id" %in% names(written_synthetic),
  identical(names(written_audit), names(result_one$margin_audit))
)
provenance <- readLines(file.path(output_directory, "provenance.txt"), warn = FALSE)
stopifnot(
  any(grepl(as.character(ARM_B_SEED), provenance, fixed = TRUE)),
  any(grepl("age_band, gender, income_band, state", provenance, fixed = TRUE)),
  any(grepl("every observed marginal count exactly", provenance, fixed = TRUE)),
  any(grepl("survey answers and individual real rows are not written", provenance, fixed = TRUE)),
  any(grepl("no model, prompt, or provider call", provenance, fixed = TRUE)),
  all(vapply(
    list.files(output_directory, full.names = TRUE),
    function(path) !any(grepl("REAL_ANSWER_SENTINEL", readLines(path, warn = FALSE), fixed = TRUE)),
    logical(1L)
  ))
)

housing_path <- tempfile(fileext = ".csv")
person_path <- tempfile(fileext = ".csv")
cli_output_directory <- tempfile(pattern = "arm-b-cli-")
utils::write.csv(housing, housing_path, row.names = FALSE)
utils::write.csv(person, person_path, row.names = FALSE)
original_parquet_reader <- read_parquet_frame
read_parquet_frame <- function(path) {
  utils::read.csv(path, check.names = FALSE, stringsAsFactors = FALSE)
}
cli_result <- NULL
invisible(capture.output(cli_result <- arm_b_main(c(
  "--housing", housing_path,
  "--person", person_path,
  "--real", real_path,
  "--output", cli_output_directory
))))
read_parquet_frame <- original_parquet_reader
stopifnot(
  cli_result$seed == ARM_B_SEED,
  nrow(cli_result$synthetic) == ARM_B_DRAW_N,
  all(file.exists(file.path(cli_output_directory, expected_outputs)))
)

unlink(
  c(
    real_path, bad_real_path, output_directory,
    housing_path, person_path, cli_output_directory
  ),
  recursive = TRUE
)

cat("test_arm_b.R: PASS\n")
