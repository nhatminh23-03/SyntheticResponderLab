baseline_path <- file.path(repo_root, "analysis", "R", "non_llm_baselines.R")
runner_path <- file.path(repo_root, "analysis", "run_non_llm_baselines.R")
source(baseline_path, local = TRUE)
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

item_columns <- paste0("Q", seq_len(32L))
respondent_n <- 600L
row_number <- seq_len(respondent_n)
real_data <- data.frame(
  respondent_id = sprintf("R%03d", row_number),
  age = 25 + row_number %% 50,
  region = rep(c("west", "south", "north"), length.out = respondent_n),
  segment = rep(c("owner", "renter"), each = 3L, length.out = respondent_n),
  stringsAsFactors = FALSE
)
for (index in seq_along(item_columns)) {
  real_data[[item_columns[[index]]]] <- as.numeric(
    1L + (row_number + index + (row_number %% 7L) * (index %% 3L)) %% 5L
  )
}

validate_baseline_data(
  real_data,
  "respondent_id",
  item_columns,
  c("region", "segment"),
  c("age", "region")
)
assert_error(
  validate_baseline_data(
    real_data[-1L, ], "respondent_id", item_columns, "region", c("age", "region")
  ),
  "Expected exactly 600 real respondents"
)
assert_error(
  validate_baseline_data(
    real_data, "respondent_id", item_columns[-1L], "region", c("age", "region")
  ),
  "Expected exactly 32 instrument item columns"
)
assert_error(
  validate_baseline_data(
    real_data, "respondent_id", item_columns, "Q1", c("age", "region")
  ),
  "Instrument items cannot also be IDs or demographic predictors"
)
invalid_items <- real_data
invalid_items$Q1 <- as.character(invalid_items$Q1)
assert_error(
  validate_baseline_data(
    invalid_items, "respondent_id", item_columns, "region", c("age", "region")
  ),
  "Instrument items must be numeric"
)
invalid_items <- real_data
invalid_items$Q1[[1L]] <- NA_real_
assert_error(
  validate_baseline_data(
    invalid_items, "respondent_id", item_columns, "region", c("age", "region")
  ),
  "Instrument items must be complete and finite"
)

split_one <- held_out_split(real_data$respondent_id, seed = 41L)
split_two <- held_out_split(real_data$respondent_id, seed = 41L)
stopifnot(
  identical(split_one, split_two),
  length(split_one$fit_index) == 300L,
  length(split_one$evaluation_index) == 300L,
  length(intersect(split_one$fit_ids, split_one$evaluation_ids)) == 0L,
  setequal(c(split_one$fit_index, split_one$evaluation_index), seq_len(600L))
)
assert_error(held_out_split(paste0("odd", 1:5)), "even number of respondents")
assert_error(assert_held_out(c("one", "two"), c("two", "three")), "Held-out violation")

result <- run_non_llm_baselines(
  real_data,
  "respondent_id",
  item_columns,
  c("region", "segment"),
  c("age", "region"),
  seed = 41L,
  k = 5L
)
stopifnot(
  identical(names(result$fits), NON_LLM_BASELINES),
  identical(names(result$predictions), NON_LLM_BASELINES),
  identical(result$split, split_one),
  nrow(result$metrics) == 5L,
  identical(result$metrics$baseline, NON_LLM_BASELINES),
  all(vapply(result$metrics[-1L], function(values) all(is.finite(values)), logical(1L))),
  all(result$audit$fit_rows == 300L),
  all(result$audit$evaluation_rows == 300L),
  all(result$audit$overlap_rows == 0L)
)

fit_data <- real_data[result$split$fit_index, , drop = FALSE]
evaluation_data <- real_data[result$split$evaluation_index, , drop = FALSE]
for (method in NON_LLM_BASELINES) {
  prediction <- result$predictions[[method]]
  stopifnot(
    nrow(prediction) == 300L,
    identical(prediction$evaluation_id, evaluation_data$respondent_id),
    identical(names(prediction)[-1L], item_columns),
    identical(result$fits[[method]]$fit_ids, fit_data$respondent_id)
  )
  assert_error(
    predict_non_llm_baseline(
      result$fits[[method]],
      fit_data[c("respondent_id", "region", "segment", "age")],
      "respondent_id"
    ),
    "Held-out violation"
  )
}

for (method in c("marginal_sampler", "gaussian_copula")) {
  prediction <- result$predictions[[method]]
  for (item in item_columns) {
    stopifnot(all(prediction[[item]] %in% fit_data[[item]]))
  }
}

repeat_result <- run_non_llm_baselines(
  real_data,
  "respondent_id",
  item_columns,
  c("region", "segment"),
  c("age", "region"),
  seed = 41L,
  k = 5L
)
stopifnot(identical(result$predictions, repeat_result$predictions))

small_fit <- data.frame(
  respondent_id = paste0("fit", 1:5),
  group = c("a", "a", "b", "b", NA),
  age = c(0, 10, 20, 30, 40),
  answer = c(1, 3, 5, 7, 9),
  constant = rep(5, 5),
  stringsAsFactors = FALSE
)
small_evaluation <- data.frame(
  respondent_id = c("evaluation_a", "evaluation_new"),
  group = c("a", "new"),
  age = c(12, NA),
  stringsAsFactors = FALSE
)

marginal_fit <- fit_marginal_sampler(
  small_fit, c("answer", "constant"), small_fit$respondent_id
)
marginal_prediction <- predict_non_llm_baseline(
  marginal_fit, small_evaluation, "respondent_id", seed = 2L
)
stopifnot(
  all(marginal_prediction$answer %in% small_fit$answer),
  identical(marginal_prediction$constant, c(5, 5))
)

normal_fit <- fit_multivariate_normal(
  small_fit, c("answer", "constant"), small_fit$respondent_id
)
normal_prediction <- predict_non_llm_baseline(
  normal_fit, small_evaluation, "respondent_id", seed = 2L
)
stopifnot(
  identical(unname(normal_fit$means), c(5, 5)),
  normal_fit$standard_deviations[[2L]] == 0,
  normal_fit$covariance[[1L, 1L]] == 1,
  normal_fit$covariance[[2L, 2L]] == 0,
  all(normal_prediction$constant == 5)
)

copula_fit <- fit_gaussian_copula(
  small_fit, c("answer", "constant"), small_fit$respondent_id
)
copula_prediction <- predict_non_llm_baseline(
  copula_fit, small_evaluation, "respondent_id", seed = 2L
)
stopifnot(
  copula_fit$latent_covariance[[1L, 1L]] == 1,
  copula_fit$latent_covariance[[2L, 2L]] == 0,
  all(copula_prediction$answer %in% small_fit$answer),
  all(copula_prediction$constant == 5)
)

target_covariance <- matrix(c(1, 0.4, 0.4, 1), nrow = 2L)
covariance_root <- matrix_square_root(target_covariance)
stopifnot(isTRUE(all.equal(
  covariance_root %*% t(covariance_root), target_covariance, tolerance = 1e-12
)))
stopifnot(identical(empirical_inverse(c(10, 20, 30), c(0, 0.5, 1)), c(10, 20, 30)))

stratum_fit <- fit_stratum_mean(
  small_fit, c("answer", "constant"), small_fit$respondent_id, "group"
)
stratum_prediction <- predict_non_llm_baseline(
  stratum_fit, small_evaluation, "respondent_id"
)
stopifnot(
  stratum_prediction$answer[[1L]] == 2,
  stratum_prediction$answer[[2L]] == mean(small_fit$answer),
  all(stratum_prediction$constant == 5)
)

knn_fit <- fit_knn_lookup(
  small_fit, c("answer", "constant"), small_fit$respondent_id, "age", k = 2L
)
knn_prediction <- predict_non_llm_baseline(knn_fit, small_evaluation, "respondent_id")
stopifnot(
  knn_prediction$answer[[1L]] == mean(c(3, 5)),
  knn_prediction$answer[[2L]] == mean(c(3, 5)),
  all(knn_prediction$constant == 5)
)
assert_error(
  fit_knn_lookup(small_fit, "answer", small_fit$respondent_id, "age", k = 0L),
  "k must be a positive integer"
)
assert_error(
  fit_knn_lookup(small_fit, "answer", small_fit$respondent_id, "age", k = 6L),
  "k-NN needs at least"
)
missing_numeric <- small_fit
missing_numeric$age <- NA_real_
assert_error(
  fit_knn_lookup(missing_numeric, "answer", missing_numeric$respondent_id, "age", k = 2L),
  "has no finite training values"
)

categorical_encoder <- fit_demographic_encoder(small_fit, "group")
encoded_new_level <- encode_demographics(small_evaluation, categorical_encoder)
stopifnot(
  all(encoded_new_level[2L, ] == 0),
  sum(encoded_new_level[1L, ]) == 1
)

known_reference <- data.frame(q1 = c(1, 2, 3), q2 = c(2, 4, 6))
known_prediction <- data.frame(q1 = c(2, 3, 4), q2 = c(4, 6, 8))
known_metrics <- evaluate_baseline(known_reference, known_prediction, c("q1", "q2"))
stopifnot(
  known_metrics$mean_rmse == sqrt(mean(c(1, 2)^2)),
  known_metrics$sd_rmse == 0,
  known_metrics$correlation_rmse == 0
)
constant_metrics <- evaluate_baseline(
  data.frame(q1 = rep(1, 3)), data.frame(q1 = rep(1, 3)), "q1"
)
stopifnot(is.na(constant_metrics$correlation_rmse))
partial_constant_metrics <- evaluate_baseline(
  data.frame(q1 = 1:5, q2 = 1:5, q3 = c(1, 3, 2, 5, 4)),
  data.frame(q1 = rep(3, 5), q2 = 1:5, q3 = c(1, 3, 2, 5, 4)),
  c("q1", "q2", "q3")
)
stopifnot(is.na(partial_constant_metrics$correlation_rmse))
assert_error(
  evaluate_baseline(known_reference, known_prediction[-1L, ], c("q1", "q2")),
  "dimensions must match"
)

bad_fit <- new_baseline_fit("not_a_method", "answer", small_fit$respondent_id, list())
assert_error(
  predict_non_llm_baseline(bad_fit, small_evaluation, "respondent_id"),
  "Unknown non-LLM baseline method"
)
assert_error(draw_gaussian(0L, diag(2L)), "positive integer")

parsed <- parse_arguments(c(
  "--input", "survey.csv",
  "--id", "respondent_id",
  "--items", paste(item_columns, collapse = ","),
  "--strata", "region, segment",
  "--knn", "age,region",
  "--seed", "17",
  "--k", "3"
))
stopifnot(
  length(parsed$items) == 32L,
  identical(parsed$strata, c("region", "segment")),
  identical(parsed$knn, c("age", "region")),
  parsed$seed == 17L,
  parsed$k == 3L
)
assert_error(parse_arguments(c("--input", "only.csv")), "Missing required arguments")
assert_error(parse_arguments(c("input", "survey.csv")), usage())

output_directory <- tempfile(pattern = "non-llm-baselines-")
input_path <- tempfile(fileext = ".csv")
utils::write.csv(real_data, input_path, row.names = FALSE)
main_result <- NULL
invisible(capture.output(main_result <- main(c(
  "--input", input_path,
  "--id", "respondent_id",
  "--items", paste(item_columns, collapse = ","),
  "--strata", "region,segment",
  "--knn", "age,region",
  "--output", output_directory,
  "--seed", "41",
  "--k", "5"
))))
expected_outputs <- c(paste0(NON_LLM_BASELINES, ".csv"), "metrics.csv", "held_out_audit.csv")
stopifnot(
  all(file.exists(file.path(output_directory, expected_outputs))),
  all(main_result$audit$overlap_rows == 0L)
)
written_prediction <- utils::read.csv(
  file.path(output_directory, "marginal_sampler.csv"), stringsAsFactors = FALSE
)
stopifnot(
  identical(written_prediction$evaluation_id, sprintf("heldout_%03d", 1:300)),
  !any(written_prediction$evaluation_id %in% real_data$respondent_id)
)
unlink(c(output_directory, input_path), recursive = TRUE)

cat("test_non_llm_baselines.R: PASS\n")
