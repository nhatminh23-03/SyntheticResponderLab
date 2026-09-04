screen_counts_path <- file.path(repo_root, "analysis", "screen_counts.R")
arm_a_path <- file.path(repo_root, "analysis", "R", "arm_a.R")
runner_path <- file.path(repo_root, "analysis", "run_arm_a.R")
source(screen_counts_path, local = TRUE)
source(arm_a_path, local = TRUE)
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

respondent_n <- 600L
housing_n <- 620L
housing <- data.frame(
  SERIALNO = sprintf("H%03d", seq_len(housing_n)),
  ST = 6,
  WGTP = 1 + seq_len(housing_n) %% 7,
  TEN = 1,
  BLD = 2,
  HINCP = 150000 + seq_len(housing_n),
  ADJINC = 1000000,
  stringsAsFactors = FALSE
)
housing$BLD[1:5] <- 3
housing$HINCP[6:10] <- 50000
housing$WGTP[16:20] <- 0

person <- data.frame(
  SERIALNO = housing$SERIALNO,
  ST = 6,
  RELSHIPP = 20,
  AGEP = 30 + seq_len(housing_n) %% 36,
  SEX = 1 + seq_len(housing_n) %% 2,
  stringsAsFactors = FALSE
)
person$AGEP[11:15] <- 29

outdoor_column <- "PQ1: outdoor-space screener"
real_data <- data.frame(
  "Response ID" = c(NA, seq_len(respondent_n)),
  Status = c(NA_character_, rep("Completed", respondent_n)),
  Gender = c("", rep(c("Female", "Male"), length.out = respondent_n)),
  Age = c(NA, rep(20:79, length.out = respondent_n)),
  "Household Income" = c("", rep(ARM_A_REAL_INCOME_LEVELS, length.out = respondent_n)),
  State = c("", ifelse(seq_len(respondent_n) %% 15L == 0L, "California", "Texas")),
  check.names = FALSE,
  stringsAsFactors = FALSE
)
real_data[[outdoor_column]] <- c(
  "",
  ifelse(seq_len(respondent_n) %% 10L == 0L, "I'm not sure, but possibly.", "Yes")
)
real_data[["Q32: real answer sentinel"]] <- c("", rep("REAL_ANSWER_SENTINEL", respondent_n))

result_one <- run_arm_a(housing, person, real_data)
result_two <- run_arm_a(housing, person, real_data)
stopifnot(
  result_one$seed == ARM_A_SEED,
  result_one$draw_n == ARM_A_DRAW_N,
  identical(result_one$synthetic, result_two$synthetic),
  nrow(result_one$synthetic) == respondent_n,
  !anyDuplicated(result_one$synthetic$synthetic_id),
  all(result_one$synthetic$age >= 30 & result_one$synthetic$age <= 65),
  all(result_one$synthetic$household_income >= 100000),
  all(result_one$synthetic$state_group == "California"),
  all(result_one$synthetic$hard_screen_proxy == "Pass all three")
)

expected_funnel <- as.integer(c(620, 620, 615, 610, 610, 605, 600, 600))
stopifnot(identical(as.integer(result_one$funnel$records), expected_funnel))

comparison_groups <- split(result_one$comparison, result_one$comparison$characteristic)
stopifnot(
  all(vapply(comparison_groups, function(frame) sum(frame$synthetic_n), integer(1L)) == respondent_n),
  all(vapply(comparison_groups, function(frame) sum(frame$real_n), integer(1L)) == respondent_n),
  all(abs(vapply(
    comparison_groups, function(frame) sum(frame$synthetic_proportion), numeric(1L)
  ) - 1) < 1e-12),
  all(abs(vapply(
    comparison_groups, function(frame) sum(frame$real_proportion), numeric(1L)
  ) - 1) < 1e-12)
)
california <- result_one$comparison[
  result_one$comparison$characteristic == "state_group" &
    result_one$comparison$level == "California",
]
stopifnot(
  california$synthetic_n == 600L,
  california$real_n == 40L,
  california$difference_percentage_points == 100 * (1 - 40 / 600)
)

real_harmonized <- harmonize_arm_a_real(real_data)
completed_real <- real_data[!is.na(real_data$Status) & real_data$Status == "Completed", ]
expected_real_pass <- sum(
  completed_real$Age >= 30 & completed_real$Age <= 65 &
    completed_real[["Household Income"]] %in%
      c("$100,000 - $199,999", "$200,000 or more") &
    completed_real[[outdoor_column]] %in% ARM_A_OUTDOOR_PASS_LEVELS
)
stopifnot(
  result_one$screen_audit$pass_all_three[[1L]] == 600L,
  result_one$screen_audit$pass_all_three[[2L]] == expected_real_pass,
  all(real_harmonized$outdoor_space_screen == "Pass"),
  isTRUE(all.equal(result_one$age_summary$synthetic[[1L]], mean(result_one$synthetic$age))),
  isTRUE(all.equal(result_one$age_summary$synthetic[[2L]], stats::sd(result_one$synthetic$age))),
  isTRUE(all.equal(result_one$age_summary$synthetic[[3L]], stats::median(result_one$synthetic$age))),
  isTRUE(all.equal(result_one$age_summary$real[[1L]], mean(real_harmonized$age))),
  isTRUE(all.equal(result_one$age_summary$real[[2L]], stats::sd(real_harmonized$age))),
  isTRUE(all.equal(result_one$age_summary$real[[3L]], stats::median(real_harmonized$age)))
)

tiny_synthetic <- data.frame(
  age = c(35, 45, 55, 62),
  gender = c("Female", "Male", "Female", "Male"),
  age_band = c("30-39", "40-49", "50-59", "60-65"),
  income_band = c(
    "$100,000 - $199,999", "$100,000 - $199,999", "$200,000 or more", "$200,000 or more"
  ),
  state_group = rep("California", 4),
  outdoor_space_screen = rep("Pass", 4),
  hard_screen_proxy = rep("Pass all three", 4),
  stringsAsFactors = FALSE
)
tiny_real <- tiny_synthetic
tiny_real$age_band[[1L]] <- "Outside 30-65"
tiny_real$income_band[[1L]] <- "Below $100,000"
tiny_real$state_group[[1L]] <- "Other state"
tiny_real$outdoor_space_screen[[1L]] <- "Does not pass"
tiny_real$hard_screen_proxy[[1L]] <- "Does not pass all three"
tiny_comparison <- compare_arm_a(tiny_synthetic, tiny_real)
age_30_39 <- tiny_comparison[
  tiny_comparison$characteristic == "age_band" & tiny_comparison$level == "30-39",
]
stopifnot(
  age_30_39$synthetic_n == 1L,
  age_30_39$real_n == 0L,
  age_30_39$difference_percentage_points == 25
)
assert_error(
  compare_arm_a(transform(tiny_synthetic, gender = "unsupported"), tiny_real),
  "outside its registered levels"
)

assert_error(
  harmonize_arm_a_real(real_data[real_data$Status != "Completed" | is.na(real_data$Status), ]),
  "Expected exactly 600 completed real respondents"
)
duplicate_real <- real_data
duplicate_real[["Response ID"]][[3L]] <- duplicate_real[["Response ID"]][[2L]]
assert_error(harmonize_arm_a_real(duplicate_real), "must be present and unique")
other_gender_real <- real_data
other_gender_real$Gender[[2L]] <- "Non-binary"
stopifnot(harmonize_arm_a_real(other_gender_real)$gender[[1L]] == "Other")
bad_real <- real_data
bad_real$Age[[2L]] <- NA_real_
assert_error(harmonize_arm_a_real(bad_real), "ages must be complete and numeric")
bad_real <- real_data
bad_real[["Household Income"]][[2L]] <- "Unknown band"
assert_error(harmonize_arm_a_real(bad_real), "unsupported levels")
bad_real <- real_data
bad_real$Gender[[2L]] <- ""
assert_error(harmonize_arm_a_real(bad_real), "gender must be present")
bad_real <- real_data
bad_real$State[[2L]] <- ""
assert_error(harmonize_arm_a_real(bad_real), "state must be present")
bad_real <- real_data
bad_real[[outdoor_column]][[2L]] <- ""
assert_error(harmonize_arm_a_real(bad_real), "outdoor-space screener must be present")
bad_real <- real_data
bad_real[[outdoor_column]][[2L]] <- "Maybe"
assert_error(harmonize_arm_a_real(bad_real), "outdoor-space screener contains unsupported levels")
assert_error(
  harmonize_arm_a_real(real_data[, names(real_data) != outdoor_column]),
  "exactly one column beginning"
)
ambiguous_real <- real_data
ambiguous_real[["PQ1: duplicate"]] <- ambiguous_real[[outdoor_column]]
assert_error(harmonize_arm_a_real(ambiguous_real), "exactly one column beginning")

raw_selected <- screen_pums_frames(housing, person, draw_n = 600L, seed = ARM_A_SEED)$selected
raw_selected$SEX[[1L]] <- 9
assert_error(harmonize_arm_a_synthetic(raw_selected), "ACS codes 1 or 2")
raw_selected <- screen_pums_frames(housing, person, draw_n = 600L, seed = ARM_A_SEED)$selected
raw_selected$ST[[1L]] <- 48
assert_error(harmonize_arm_a_synthetic(raw_selected), "only California PUMS records")
raw_selected <- screen_pums_frames(housing, person, draw_n = 600L, seed = ARM_A_SEED)$selected
raw_selected$AGEP[[1L]] <- 66
assert_error(harmonize_arm_a_synthetic(raw_selected), "violates the inclusive age 30-65 screen")
raw_selected <- screen_pums_frames(housing, person, draw_n = 600L, seed = ARM_A_SEED)$selected
raw_selected$household_income[[1L]] <- 99999
assert_error(harmonize_arm_a_synthetic(raw_selected), "violates the adjusted $100,000 income screen")
raw_selected <- screen_pums_frames(housing, person, draw_n = 600L, seed = ARM_A_SEED)$selected
raw_selected$BLD[[1L]] <- 3
assert_error(harmonize_arm_a_synthetic(raw_selected), "violates the detached single-family screen")
raw_selected <- screen_pums_frames(housing, person, draw_n = 600L, seed = ARM_A_SEED)$selected
raw_selected$WGTP[[1L]] <- 0
assert_error(harmonize_arm_a_synthetic(raw_selected), "finite, positive WGTP")
assert_error(harmonize_arm_a_synthetic(raw_selected[FALSE, ]), "contains no respondents")
assert_error(
  harmonize_arm_a_synthetic(raw_selected[, names(raw_selected) != "ST"]),
  "missing required columns: ST"
)

# Validate the complete source frames before drawing. Otherwise an eligible out-of-state row with
# a negligible weight can change the sampling frame, evade selection, and bypass selected-row
# validation entirely.
mixed_state_housing <- rbind(
  housing,
  data.frame(
    SERIALNO = "OUT_OF_STATE",
    ST = 48,
    WGTP = .Machine$double.xmin,
    TEN = 1,
    BLD = 2,
    HINCP = 150000,
    ADJINC = 1000000,
    stringsAsFactors = FALSE
  )
)
mixed_state_person <- rbind(
  person,
  data.frame(
    SERIALNO = "OUT_OF_STATE",
    ST = 48,
    RELSHIPP = 20,
    AGEP = 45,
    SEX = 1,
    stringsAsFactors = FALSE
  )
)
old_path_draw <- screen_pums_frames(
  mixed_state_housing,
  mixed_state_person,
  draw_n = ARM_A_DRAW_N,
  seed = ARM_A_SEED
)$selected
stopifnot(!any(arm_a_number(old_path_draw$ST) != 6))
assert_error(
  run_arm_a(mixed_state_housing, mixed_state_person, real_data),
  "housing PUMS frame must contain only California records"
)

wrong_person_state <- person
wrong_person_state$ST[[1L]] <- 48
assert_error(
  run_arm_a(housing, wrong_person_state, real_data),
  "person PUMS frame must contain only California records"
)

parsed <- parse_arm_a_arguments(c(
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
default_parsed <- parse_arm_a_arguments(c(
  "--housing", "housing.parquet", "--person", "person.parquet", "--real", "real.csv"
))
stopifnot(default_parsed$output == file.path("analysis", "output", "arm_a"))
assert_error(parse_arm_a_arguments(c("--housing", "only.parquet")), "Missing required arguments")
assert_error(parse_arm_a_arguments(c("housing", "file")), arm_a_usage())
assert_error(
  parse_arm_a_arguments(c("--housing", "h", "--person", "p", "--real", "r", "--seed", "1")),
  "Unknown arguments: seed"
)
assert_error(
  parse_arm_a_arguments(c(
    "--housing", "one", "--housing", "two", "--person", "p", "--real", "r"
  )),
  "was supplied more than once"
)
assert_error(
  arm_a_main(c("--housing", "missing-housing", "--person", "missing-person", "--real", "missing-real")),
  "Arm A input was not found"
)

output_directory <- tempfile(pattern = "arm-a-")
write_arm_a_results(
  result_one,
  output_directory,
  list(housing = "housing-source", person = "person-source", real = "real-source")
)
expected_outputs <- c(
  "synthetic_respondents.csv",
  "comparison.csv",
  "age_summary.csv",
  "screen_audit.csv",
  "screen_funnel.csv",
  "provenance.txt"
)
stopifnot(all(file.exists(file.path(output_directory, expected_outputs))))
written_synthetic <- utils::read.csv(
  file.path(output_directory, "synthetic_respondents.csv"),
  stringsAsFactors = FALSE
)
written_comparison <- utils::read.csv(
  file.path(output_directory, "comparison.csv"),
  stringsAsFactors = FALSE
)
stopifnot(
  nrow(written_synthetic) == 600L,
  !"Response ID" %in% names(written_synthetic),
  identical(names(written_comparison), names(result_one$comparison)),
  setequal(
    names(written_comparison),
    c(
      "characteristic", "level", "synthetic_n", "synthetic_proportion",
      "real_n", "real_proportion", "difference_percentage_points"
    )
  )
)
provenance <- readLines(file.path(output_directory, "provenance.txt"), warn = FALSE)
stopifnot(
  any(grepl(as.character(ARM_A_SEED), provenance, fixed = TRUE)),
  any(grepl("individual real rows and survey answers are not written", provenance, fixed = TRUE)),
  any(grepl("no model or provider calls", provenance, fixed = TRUE)),
  any(grepl("Housing source: housing-source", provenance, fixed = TRUE)),
  all(vapply(
    list.files(output_directory, full.names = TRUE),
    function(path) !any(grepl("REAL_ANSWER_SENTINEL", readLines(path, warn = FALSE), fixed = TRUE)),
    logical(1L)
  ))
)

housing_path <- tempfile(fileext = ".csv")
person_path <- tempfile(fileext = ".csv")
real_path <- tempfile(fileext = ".csv")
cli_output_directory <- tempfile(pattern = "arm-a-cli-")
utils::write.csv(housing, housing_path, row.names = FALSE)
utils::write.csv(person, person_path, row.names = FALSE)
utils::write.csv(real_data, real_path, row.names = FALSE)
original_parquet_reader <- read_parquet_frame
read_parquet_frame <- function(path) {
  utils::read.csv(path, check.names = FALSE, stringsAsFactors = FALSE)
}
cli_result <- NULL
invisible(capture.output(cli_result <- arm_a_main(c(
  "--housing", housing_path,
  "--person", person_path,
  "--real", real_path,
  "--output", cli_output_directory
))))
read_parquet_frame <- original_parquet_reader
stopifnot(
  cli_result$seed == ARM_A_SEED,
  nrow(cli_result$synthetic) == ARM_A_DRAW_N,
  all(file.exists(file.path(cli_output_directory, expected_outputs)))
)
unlink(c(housing_path, person_path, real_path, cli_output_directory), recursive = TRUE)
unlink(output_directory, recursive = TRUE)

cat("test_arm_a.R: PASS\n")
