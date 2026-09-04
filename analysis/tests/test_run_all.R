runner_path <- file.path(repo_root, "analysis", "run_all.R")
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

default_options <- parse_run_all_arguments(character(), repo_root = repo_root)
stopifnot(
  default_options[["arm-a-housing"]] == file.path(repo_root, "analysis", "data", "arm_a_housing.parquet"),
  default_options[["arm-b-person"]] == file.path(repo_root, "analysis", "data", "arm_b_person.parquet"),
  default_options$real == file.path(repo_root, "analysis", "data", "real_responses.csv"),
  default_options$synthetic == file.path(repo_root, "analysis", "data", "synthetic_responses.csv"),
  default_options$registry == file.path(repo_root, "analysis", "data", "question_registry.csv"),
  identical(default_options$strata, c("Gender", "Household Income", "State")),
  identical(default_options$knn, c("Age", "Gender", "Household Income", "State")),
  default_options$output == file.path(repo_root, "analysis", "output", "validation_report.html")
)

parsed <- parse_run_all_arguments(c(
  "--arm-a-housing", "a-housing.csv",
  "--arm-a-person", "a-person.csv",
  "--arm-b-housing", "b-housing.csv",
  "--arm-b-person", "b-person.csv",
  "--real", "real.csv",
  "--synthetic", "synthetic.csv",
  "--registry", "registry.csv",
  "--real-id", "real_id",
  "--synthetic-id", "synthetic_id",
  "--strata", "region, segment",
  "--knn", "age,region",
  "--output", "report.html"
), repo_root = repo_root)
stopifnot(
  parsed[["arm-a-housing"]] == "a-housing.csv",
  parsed[["arm-b-person"]] == "b-person.csv",
  parsed[["real-id"]] == "real_id",
  parsed[["synthetic-id"]] == "synthetic_id",
  identical(parsed$strata, c("region", "segment")),
  identical(parsed$knn, c("age", "region")),
  parsed$output == "report.html"
)
assert_error(parse_run_all_arguments("--real", repo_root), run_all_usage())
assert_error(parse_run_all_arguments(c("real", "file.csv"), repo_root), run_all_usage())
assert_error(
  parse_run_all_arguments(c("--real", "one.csv", "--real", "two.csv"), repo_root),
  "was supplied more than once"
)
assert_error(parse_run_all_arguments(c("--seed", "1"), repo_root), "Unknown arguments: seed")
assert_error(parse_run_all_arguments(c("--strata", ","), repo_root), "must name one or more unique")
assert_error(parse_run_all_arguments(c("--knn", "Age,Age"), repo_root), "must name one or more unique")
assert_error(parse_run_all_arguments(c("--output", "report.pdf"), repo_root), "must end in .html")

stopifnot(
  identical(html_escape("<tag a='b'>&\""), "&lt;tag a=&#39;b&#39;&gt;&amp;&quot;"),
  identical(format_report_values(c(TRUE, FALSE, NA)), c("Yes", "No", "—")),
  identical(format_report_values(c("value", "", NA)), c("value", "—", "—"))
)
assert_error(report_html_table(list(value = 1)), "require a data frame")
empty_table <- report_html_table(data.frame(value = character()))
stopifnot(grepl("No rows", empty_table, fixed = TRUE))
assert_error(write_validation_report(list(), "report.txt"), "ending in .html")
assert_error(report_input_manifest(stats::setNames("missing", "")), "uniquely named")
assert_error(report_input_manifest(c(input = "missing")), "Report input was not found")
assert_error(report_seed_register(character(), 1L), "named baseline methods")
assert_error(report_seed_register("method", 0L), "positive integer question count")

respondent_n <- 600L
arm_a_housing_n <- 620L
arm_a_housing <- data.frame(
  SERIALNO = sprintf("A%04d", seq_len(arm_a_housing_n)),
  ST = 6,
  WGTP = 1 + seq_len(arm_a_housing_n) %% 11L,
  TEN = 1,
  BLD = 2,
  HINCP = 150000 + seq_len(arm_a_housing_n),
  ADJINC = 1000000,
  stringsAsFactors = FALSE
)
arm_a_person <- data.frame(
  SERIALNO = arm_a_housing$SERIALNO,
  ST = 6,
  RELSHIPP = 20,
  AGEP = 30 + seq_len(arm_a_housing_n) %% 36L,
  SEX = 1 + seq_len(arm_a_housing_n) %% 2L,
  stringsAsFactors = FALSE
)

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
arm_b_housing <- data.frame(
  SERIALNO = sprintf("B%05d", seq_len(nrow(donors))),
  ST = donors$state,
  WGTP = 1 + (seq_len(nrow(donors)) * 7L) %% 23L,
  TEN = 1,
  HINCP = donors$income,
  ADJINC = 1000000,
  stringsAsFactors = FALSE
)
arm_b_person <- data.frame(
  SERIALNO = arm_b_housing$SERIALNO,
  ST = donors$state,
  RELSHIPP = 20,
  AGEP = donors$age,
  SEX = donors$sex,
  stringsAsFactors = FALSE
)

real_age <- rep(age_values, length.out = respondent_n)
real_gender <- rep(c("Female", "Male"), each = respondent_n / 2L)
real_income <- rep(ARM_B_INCOME_LEVELS, each = respondent_n / length(ARM_B_INCOME_LEVELS))
real_state <- rep(c("California", "New York", "Ohio", "Texas"), times = c(40, 180, 120, 260))
real_completed <- data.frame(
  "Response ID" = sprintf("real_%03d", seq_len(respondent_n)),
  Status = "Completed",
  Gender = real_gender,
  Age = real_age,
  "Household Income" = real_income,
  State = real_state,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
real_completed[["PQ1: outdoor-space screener"]] <- "Yes"
continuous_items <- sprintf("Q%02d", 1:30)
for (index in seq_along(continuous_items)) {
  real_completed[[continuous_items[[index]]]] <-
    real_age / 10 + (real_gender == "Male") * 0.2 +
    ((seq_len(respondent_n) + index) %% 5L) / 10 + index / 100
}
real_completed$Q31 <- rep(c(0, 1), length.out = respondent_n)
real_completed$Q32 <- rep(1:3, length.out = respondent_n)
real_completed$private_answer_sentinel <- "REAL_ANSWER_SENTINEL"

blank_row <- real_completed[1L, , drop = FALSE]
blank_row[] <- NA
real_data <- rbind(blank_row, real_completed)
synthetic_data <- real_completed[c("Response ID", continuous_items, "Q31", "Q32")]
names(synthetic_data)[[1L]] <- "synthetic_id"
synthetic_data$synthetic_id <- sprintf("synthetic_%03d", seq_len(respondent_n))
names(real_data)[names(real_data) == "Response ID"] <- "real_id"
for (item in continuous_items) {
  synthetic_data[[item]] <- synthetic_data[[item]] + 0.02
}
synthetic_data$Q31 <- c(rep(0, 290L), rep(1, 310L))
synthetic_data$Q32 <- rep(c(1, 2, 3), times = c(205, 195, 200))

item_columns <- c(continuous_items, "Q31", "Q32")
registry <- data.frame(
  question_id = item_columns,
  question_type = c(rep("continuous", 30L), "binary", "categorical"),
  equivalence_margin = c(rep(1, 30L), 0.2, 0.2),
  positive_level = c(rep("", 30L), "1", ""),
  stringsAsFactors = FALSE
)

workspace <- tempfile(pattern = "run-all-")
dir.create(workspace)
paths <- file.path(workspace, c(
  "arm-a-housing.csv", "arm-a-person.csv", "arm-b-housing.csv", "arm-b-person.csv",
  "real.csv", "synthetic.csv", "registry.csv"
))
frames <- list(
  arm_a_housing,
  arm_a_person,
  arm_b_housing,
  arm_b_person,
  real_data,
  synthetic_data,
  registry
)
for (index in seq_along(paths)) {
  utils::write.csv(frames[[index]], paths[[index]], row.names = FALSE, na = "")
}
output_directory <- file.path(workspace, "output")
output_path <- file.path(output_directory, "validation.html")

arguments <- c(
  "--arm-a-housing", paths[[1L]],
  "--arm-a-person", paths[[2L]],
  "--arm-b-housing", paths[[3L]],
  "--arm-b-person", paths[[4L]],
  "--real", paths[[5L]],
  "--synthetic", paths[[6L]],
  "--registry", paths[[7L]],
  "--real-id", "real_id",
  "--synthetic-id", "synthetic_id",
  "--strata", "Gender",
  "--knn", "Age,Gender",
  "--output", output_path
)
result <- NULL
invisible(capture.output(result <- run_all_main(arguments)))
stopifnot(
  file.exists(output_path),
  result$arm_a$seed == ARM_A_SEED,
  result$arm_b$seed == ARM_B_SEED,
  nrow(result$arm_a$synthetic) == respondent_n,
  nrow(result$arm_b$synthetic) == respondent_n,
  identical(result$baselines$audit$baseline, NON_LLM_BASELINES),
  all(result$baselines$audit$overlap_rows == 0L),
  identical(result$battery$results$question_id, item_columns),
  identical(
    result$battery$results$test[c(1L, 31L, 32L)],
    c(
      "Welch two-sample t-test",
      "two-sample Wald z-test",
      "Pearson chi-square test of homogeneity"
    )
  ),
  all(c("Complete", "Blocked") %in% result$coverage$status),
  nrow(result$inputs) == 7L,
  all(nchar(result$inputs$md5) == 32L)
)

html_one <- paste(readLines(output_path, warn = FALSE), collapse = "\n")
second_result <- NULL
invisible(capture.output(second_result <- run_all_main(arguments)))
html_two <- paste(readLines(output_path, warn = FALSE), collapse = "\n")
stopifnot(
  identical(html_one, html_two),
  identical(result$arm_a$synthetic, second_result$arm_a$synthetic),
  identical(result$arm_b$synthetic, second_result$arm_b$synthetic),
  identical(result$baselines$metrics, second_result$baselines$metrics),
  identical(result$battery$results, second_result$battery$results),
  grepl("Arm A — hard-screened draw", html_one, fixed = TRUE),
  grepl("Arm B — distribution-matched draw", html_one, fixed = TRUE),
  grepl("Arm C — convenience-sample match", html_one, fixed = TRUE),
  grepl("Non-LLM response baseline arm", html_one, fixed = TRUE),
  grepl("Welch two-sample t-test", html_one, fixed = TRUE),
  grepl("two-sample Wald z-test", html_one, fixed = TRUE),
  grepl("Pearson chi-square test of homogeneity", html_one, fixed = TRUE),
  grepl("All per-estimand TOST results", html_one, fixed = TRUE),
  grepl(as.character(ARM_A_SEED), html_one, fixed = TRUE),
  grepl("no model or provider calls", html_one, fixed = TRUE),
  !grepl("REAL_ANSWER_SENTINEL", html_one, fixed = TRUE),
  !grepl(normalizePath(paths[[5L]]), html_one, fixed = TRUE),
  identical(list.files(output_directory, pattern = "\\.html$"), "validation.html")
)

bad_status <- real_data
first_completed <- which(bad_status$Status == "Completed")[[1L]]
bad_status$Status[[first_completed]] <- "Incomplete"
assert_error(report_completed_responses(bad_status), "Expected exactly 600 completed")
unlink(workspace, recursive = TRUE)

cat("test_run_all.R: PASS\n")
