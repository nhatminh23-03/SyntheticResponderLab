TEST_BATTERY_ALPHA <- 0.05
TEST_BATTERY_CONFIDENCE_LEVEL <- 0.95
TEST_BATTERY_BOOTSTRAP_REPLICATES <- 2000L
TEST_BATTERY_SEED <- 20260904L
TEST_BATTERY_QUESTION_TYPES <- c("continuous", "binary", "categorical")

test_battery_require_columns <- function(frame, columns, label) {
  missing <- setdiff(columns, names(frame))
  if (length(missing) > 0L) {
    stop(sprintf("%s is missing required columns: %s", label, paste(missing, collapse = ", ")))
  }
  name_counts <- table(names(frame))
  duplicated_required <- unique(columns[columns %in% names(name_counts[name_counts > 1L])])
  if (length(duplicated_required) > 0L) {
    stop(sprintf(
      "%s has ambiguous duplicate required columns: %s",
      label,
      paste(duplicated_required, collapse = ", ")
    ))
  }
}

test_battery_number <- function(values) {
  suppressWarnings(as.numeric(as.character(values)))
}

validate_question_registry <- function(registry) {
  test_battery_require_columns(
    registry,
    c("question_id", "question_type", "equivalence_margin"),
    "Question registry"
  )
  if (nrow(registry) == 0L) {
    stop("Question registry must contain at least one analyzable question.")
  }

  question_id <- trimws(as.character(registry$question_id))
  question_type <- tolower(trimws(as.character(registry$question_type)))
  equivalence_margin <- test_battery_number(registry$equivalence_margin)
  if (any(is.na(registry$question_id)) || any(question_id == "") || anyDuplicated(question_id)) {
    stop("Question registry question_id values must be present and unique.")
  }
  unsupported <- setdiff(unique(question_type), TEST_BATTERY_QUESTION_TYPES)
  if (length(unsupported) > 0L || any(is.na(registry$question_type))) {
    stop(sprintf(
      "Question registry contains unsupported question types: %s. Use continuous, binary, or categorical.",
      paste(unsupported, collapse = ", ")
    ))
  }
  if (any(!is.finite(equivalence_margin)) || any(equivalence_margin <= 0)) {
    stop("Every question must have one finite, positive pre-registered equivalence_margin.")
  }
  proportion_margin <- question_type %in% c("binary", "categorical")
  if (any(equivalence_margin[proportion_margin] >= 1)) {
    stop("Binary and categorical equivalence margins must be proportions strictly between 0 and 1.")
  }

  positive_level <- rep(NA_character_, nrow(registry))
  if ("positive_level" %in% names(registry)) {
    positive_level <- trimws(as.character(registry$positive_level))
    positive_level[is.na(registry$positive_level) | positive_level == ""] <- NA_character_
  }
  if (any(question_type == "binary" & is.na(positive_level))) {
    stop("Every binary question must declare a positive_level in the question registry.")
  }

  data.frame(
    question_id = question_id,
    question_type = question_type,
    equivalence_margin = equivalence_margin,
    positive_level = positive_level,
    stringsAsFactors = FALSE
  )
}

validate_test_battery_responses <- function(frame, id_column, question_ids, label) {
  test_battery_require_columns(frame, c(id_column, question_ids), label)
  ids <- trimws(as.character(frame[[id_column]]))
  if (nrow(frame) < 2L) {
    stop(sprintf("%s must contain at least two respondents.", label))
  }
  if (any(is.na(frame[[id_column]])) || any(ids == "") || anyDuplicated(ids)) {
    stop(sprintf("%s respondent IDs must be present and unique.", label))
  }
  invisible(TRUE)
}

test_battery_continuous <- function(values, question_id, sample_label) {
  numeric_values <- test_battery_number(values)
  if (any(!is.finite(numeric_values))) {
    stop(sprintf("%s %s responses must be complete, finite numbers.", sample_label, question_id))
  }
  numeric_values
}

test_battery_discrete <- function(values, question_id, sample_label) {
  normalized <- trimws(as.character(values))
  if (any(is.na(values)) || any(normalized == "")) {
    stop(sprintf("%s %s responses must be complete, non-blank categories.", sample_label, question_id))
  }
  normalized
}

welch_degrees_of_freedom <- function(real, synthetic) {
  real_component <- stats::var(real) / length(real)
  synthetic_component <- stats::var(synthetic) / length(synthetic)
  numerator <- (real_component + synthetic_component)^2
  denominator <- real_component^2 / (length(real) - 1L) +
    synthetic_component^2 / (length(synthetic) - 1L)
  numerator / denominator
}

test_battery_tost <- function(estimate, standard_error, margin, alpha, degrees_of_freedom = Inf) {
  if (!is.finite(standard_error) || standard_error <= 0) {
    stop("TOST requires a finite, positive standard error.")
  }
  if (is.finite(degrees_of_freedom)) {
    critical <- stats::qt(1 - alpha, degrees_of_freedom)
    p_lower <- stats::pt((estimate + margin) / standard_error, degrees_of_freedom, lower.tail = FALSE)
    p_upper <- stats::pt((estimate - margin) / standard_error, degrees_of_freedom)
  } else {
    critical <- stats::qnorm(1 - alpha)
    p_lower <- stats::pnorm((estimate + margin) / standard_error, lower.tail = FALSE)
    p_upper <- stats::pnorm((estimate - margin) / standard_error)
  }
  data.frame(
    estimate = estimate,
    confidence_level = 1 - 2 * alpha,
    confidence_lower = estimate - critical * standard_error,
    confidence_upper = estimate + critical * standard_error,
    p_lower = p_lower,
    p_upper = p_upper,
    p_value = max(p_lower, p_upper),
    equivalent = p_lower < alpha && p_upper < alpha,
    stringsAsFactors = FALSE
  )
}

hedges_g <- function(real, synthetic, confidence_level) {
  real_n <- length(real)
  synthetic_n <- length(synthetic)
  degrees_of_freedom <- real_n + synthetic_n - 2L
  pooled_variance <- (
    (real_n - 1L) * stats::var(real) + (synthetic_n - 1L) * stats::var(synthetic)
  ) / degrees_of_freedom
  if (!is.finite(pooled_variance) || pooled_variance <= 0) {
    stop("Continuous comparison requires positive pooled variance for Hedges' g.")
  }
  cohen_d <- (mean(real) - mean(synthetic)) / sqrt(pooled_variance)
  correction <- 1 - 3 / (4 * degrees_of_freedom - 1)
  estimate <- correction * cohen_d
  standard_error <- sqrt(
    correction^2 * (real_n + synthetic_n) / (real_n * synthetic_n) +
      estimate^2 / (2 * degrees_of_freedom)
  )
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  c(
    estimate = estimate,
    confidence_lower = estimate - critical * standard_error,
    confidence_upper = estimate + critical * standard_error
  )
}

continuous_question_test <- function(real, synthetic, margin, alpha, confidence_level) {
  standard_error <- sqrt(stats::var(real) / length(real) + stats::var(synthetic) / length(synthetic))
  if (!is.finite(standard_error) || standard_error <= 0) {
    stop("Continuous comparison requires a finite, positive Welch standard error.")
  }
  degrees_of_freedom <- welch_degrees_of_freedom(real, synthetic)
  estimate <- mean(real) - mean(synthetic)
  statistic <- estimate / standard_error
  critical <- stats::qt(1 - (1 - confidence_level) / 2, degrees_of_freedom)
  standardized <- hedges_g(real, synthetic, confidence_level)
  tost <- test_battery_tost(estimate, standard_error, margin, alpha, degrees_of_freedom)

  list(
    test = "Welch two-sample t-test",
    effect_size = "mean_difference_real_minus_synthetic",
    effect_estimate = estimate,
    confidence_lower = estimate - critical * standard_error,
    confidence_upper = estimate + critical * standard_error,
    standardized_effect_size = "hedges_g",
    standardized_effect_estimate = unname(standardized[["estimate"]]),
    standardized_confidence_lower = unname(standardized[["confidence_lower"]]),
    standardized_confidence_upper = unname(standardized[["confidence_upper"]]),
    statistic = statistic,
    degrees_of_freedom = degrees_of_freedom,
    p_value = 2 * stats::pt(abs(statistic), degrees_of_freedom, lower.tail = FALSE),
    tost = tost,
    tost_estimand = "mean_difference_real_minus_synthetic",
    assumption_note = "Welch unequal-variance inference; Hedges' g CI uses a large-sample standard-error approximation."
  )
}

wald_proportion_comparison <- function(real_positive, synthetic_positive, confidence_level) {
  real_n <- length(real_positive)
  synthetic_n <- length(synthetic_positive)
  real_proportion <- mean(real_positive)
  synthetic_proportion <- mean(synthetic_positive)
  estimate <- real_proportion - synthetic_proportion
  standard_error <- sqrt(
    real_proportion * (1 - real_proportion) / real_n +
      synthetic_proportion * (1 - synthetic_proportion) / synthetic_n
  )
  if (!is.finite(standard_error) || standard_error <= 0) {
    stop("Wald comparison requires a finite, positive unpooled standard error.")
  }
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  list(
    estimate = estimate,
    standard_error = standard_error,
    confidence_lower = estimate - critical * standard_error,
    confidence_upper = estimate + critical * standard_error,
    statistic = estimate / standard_error
  )
}

binary_question_test <- function(real, synthetic, positive_level, margin, alpha, confidence_level) {
  levels <- sort(unique(c(real, synthetic)))
  if (length(levels) != 2L) {
    stop("Binary comparison requires exactly two observed response levels across both samples.")
  }
  if (!positive_level %in% levels) {
    stop(sprintf("Registered binary positive_level %s is not observed.", shQuote(positive_level)))
  }
  comparison <- wald_proportion_comparison(real == positive_level, synthetic == positive_level, confidence_level)
  tost <- test_battery_tost(comparison$estimate, comparison$standard_error, margin, alpha)
  counts <- rbind(
    real = as.numeric(table(factor(real, levels = levels))),
    synthetic = as.numeric(table(factor(synthetic, levels = levels)))
  )
  expected <- outer(rowSums(counts), colSums(counts)) / sum(counts)
  note <- if (min(expected) < 5) {
    sprintf("Wald normal approximation is weak: minimum expected cell count is %.3f.", min(expected))
  } else {
    sprintf("Wald normal approximation check passed: minimum expected cell count is %.3f.", min(expected))
  }

  list(
    test = "two-sample Wald z-test",
    effect_size = "risk_difference_real_minus_synthetic",
    effect_estimate = comparison$estimate,
    confidence_lower = comparison$confidence_lower,
    confidence_upper = comparison$confidence_upper,
    standardized_effect_size = NA_character_,
    standardized_effect_estimate = NA_real_,
    standardized_confidence_lower = NA_real_,
    standardized_confidence_upper = NA_real_,
    statistic = comparison$statistic,
    degrees_of_freedom = NA_real_,
    p_value = 2 * stats::pnorm(abs(comparison$statistic), lower.tail = FALSE),
    tost = tost,
    tost_estimand = sprintf("risk_difference_for_%s", positive_level),
    assumption_note = note
  )
}

cramers_v_from_counts <- function(counts) {
  counts <- counts[, colSums(counts) > 0, drop = FALSE]
  if (ncol(counts) < 2L) {
    return(0)
  }
  expected <- outer(rowSums(counts), colSums(counts)) / sum(counts)
  statistic <- sum((counts - expected)^2 / expected)
  sqrt(statistic / (sum(counts) * min(nrow(counts) - 1L, ncol(counts) - 1L)))
}

with_test_battery_seed <- function(seed, expression) {
  had_seed <- exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  if (had_seed) {
    previous_seed <- get(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  }
  on.exit({
    if (had_seed) {
      assign(".Random.seed", previous_seed, envir = .GlobalEnv)
    } else if (exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)) {
      rm(".Random.seed", envir = .GlobalEnv)
    }
  }, add = TRUE)
  set.seed(seed)
  force(expression)
}

bootstrap_cramers_v <- function(real, synthetic, levels, replicates, seed, confidence_level) {
  estimates <- with_test_battery_seed(seed, replicate(replicates, {
    sampled_real <- sample(real, length(real), replace = TRUE)
    sampled_synthetic <- sample(synthetic, length(synthetic), replace = TRUE)
    counts <- rbind(
      real = as.numeric(table(factor(sampled_real, levels = levels))),
      synthetic = as.numeric(table(factor(sampled_synthetic, levels = levels)))
    )
    cramers_v_from_counts(counts)
  }))
  observed_counts <- rbind(
    real = as.numeric(table(factor(real, levels = levels))),
    synthetic = as.numeric(table(factor(synthetic, levels = levels)))
  )
  observed <- cramers_v_from_counts(observed_counts)
  standard_error <- stats::sd(estimates)
  critical <- stats::qnorm(1 - (1 - confidence_level) / 2)
  c(
    max(0, observed - critical * standard_error),
    min(1, observed + critical * standard_error)
  )
}

categorical_question_test <- function(
  real,
  synthetic,
  margin,
  alpha,
  confidence_level,
  bootstrap_replicates,
  seed
) {
  levels <- sort(unique(c(real, synthetic)))
  if (length(levels) < 2L) {
    stop("Categorical comparison requires at least two observed response levels across both samples.")
  }
  counts <- rbind(
    real = as.numeric(table(factor(real, levels = levels))),
    synthetic = as.numeric(table(factor(synthetic, levels = levels)))
  )
  colnames(counts) <- levels
  expected <- outer(rowSums(counts), colSums(counts)) / sum(counts)
  statistic <- sum((counts - expected)^2 / expected)
  degrees_of_freedom <- ncol(counts) - 1L
  effect_estimate <- cramers_v_from_counts(counts)
  effect_ci <- bootstrap_cramers_v(
    real,
    synthetic,
    levels,
    bootstrap_replicates,
    seed,
    confidence_level
  )

  tost_rows <- lapply(levels, function(level) {
    comparison <- wald_proportion_comparison(real == level, synthetic == level, confidence_level)
    tost <- test_battery_tost(comparison$estimate, comparison$standard_error, margin, alpha)
    data.frame(level = level, tost, stringsAsFactors = FALSE)
  })
  tost <- do.call(rbind, tost_rows)
  rownames(tost) <- NULL
  note <- if (min(expected) < 5) {
    sprintf("Chi-square approximation is weak: minimum expected cell count is %.3f.", min(expected))
  } else {
    sprintf("Chi-square approximation check passed: minimum expected cell count is %.3f.", min(expected))
  }

  list(
    test = "Pearson chi-square test of homogeneity",
    effect_size = "cramers_v",
    effect_estimate = effect_estimate,
    confidence_lower = effect_ci[[1L]],
    confidence_upper = effect_ci[[2L]],
    standardized_effect_size = NA_character_,
    standardized_effect_estimate = NA_real_,
    standardized_confidence_lower = NA_real_,
    standardized_confidence_upper = NA_real_,
    statistic = statistic,
    degrees_of_freedom = degrees_of_freedom,
    p_value = stats::pchisq(statistic, degrees_of_freedom, lower.tail = FALSE),
    tost = tost,
    tost_estimand = "category_proportion_difference_real_minus_synthetic",
    assumption_note = note
  )
}

test_battery_result_row <- function(question, comparison, confidence_level, real_n, synthetic_n) {
  tost <- comparison$tost
  data.frame(
    question_id = question$question_id,
    question_type = question$question_type,
    real_n = real_n,
    synthetic_n = synthetic_n,
    test = comparison$test,
    effect_size = comparison$effect_size,
    effect_estimate = comparison$effect_estimate,
    confidence_level = confidence_level,
    confidence_lower = comparison$confidence_lower,
    confidence_upper = comparison$confidence_upper,
    standardized_effect_size = comparison$standardized_effect_size,
    standardized_effect_estimate = comparison$standardized_effect_estimate,
    standardized_confidence_lower = comparison$standardized_confidence_lower,
    standardized_confidence_upper = comparison$standardized_confidence_upper,
    statistic = comparison$statistic,
    degrees_of_freedom = comparison$degrees_of_freedom,
    p_value = comparison$p_value,
    equivalence_margin = question$equivalence_margin,
    tost_confidence_level = unique(tost$confidence_level),
    tost_p_value = max(tost$p_value),
    equivalent = all(tost$equivalent),
    assumption_note = comparison$assumption_note,
    stringsAsFactors = FALSE
  )
}

test_battery_tost_rows <- function(question, comparison) {
  tost <- comparison$tost
  level <- if ("level" %in% names(tost)) tost$level else rep(NA_character_, nrow(tost))
  data.frame(
    question_id = question$question_id,
    question_type = question$question_type,
    estimand = comparison$tost_estimand,
    level = level,
    effect_estimate = tost$estimate,
    equivalence_margin = question$equivalence_margin,
    confidence_level = tost$confidence_level,
    confidence_lower = tost$confidence_lower,
    confidence_upper = tost$confidence_upper,
    p_lower = tost$p_lower,
    p_upper = tost$p_upper,
    p_value = tost$p_value,
    equivalent = tost$equivalent,
    stringsAsFactors = FALSE
  )
}

run_test_battery <- function(
  real_data,
  synthetic_data,
  registry,
  real_id_column,
  synthetic_id_column,
  alpha = TEST_BATTERY_ALPHA,
  confidence_level = TEST_BATTERY_CONFIDENCE_LEVEL,
  bootstrap_replicates = TEST_BATTERY_BOOTSTRAP_REPLICATES,
  seed = TEST_BATTERY_SEED
) {
  if (length(alpha) != 1L || !is.finite(alpha) || alpha <= 0 || alpha >= 0.5) {
    stop("Test battery alpha must be one finite number strictly between 0 and 0.5.")
  }
  if (length(confidence_level) != 1L || !is.finite(confidence_level) ||
      confidence_level <= 0 || confidence_level >= 1) {
    stop("Test battery confidence_level must be one finite number strictly between 0 and 1.")
  }
  if (length(bootstrap_replicates) != 1L || is.na(bootstrap_replicates) ||
      bootstrap_replicates < 100L || bootstrap_replicates != as.integer(bootstrap_replicates)) {
    stop("Test battery bootstrap_replicates must be an integer of at least 100.")
  }
  if (length(seed) != 1L || is.na(seed) || seed != as.integer(seed)) {
    stop("Test battery seed must be one integer.")
  }

  registry <- validate_question_registry(registry)
  if (real_id_column %in% registry$question_id) {
    stop("Real response ID column must not also be a registered question column.")
  }
  if (synthetic_id_column %in% registry$question_id) {
    stop("Synthetic response ID column must not also be a registered question column.")
  }
  validate_test_battery_responses(real_data, real_id_column, registry$question_id, "Real response frame")
  validate_test_battery_responses(
    synthetic_data,
    synthetic_id_column,
    registry$question_id,
    "Synthetic response frame"
  )

  result_rows <- vector("list", nrow(registry))
  tost_rows <- vector("list", nrow(registry))
  for (index in seq_len(nrow(registry))) {
    question <- registry[index, , drop = FALSE]
    question_id <- question$question_id[[1L]]
    question_type <- question$question_type[[1L]]
    margin <- question$equivalence_margin[[1L]]

    if (question_type == "continuous") {
      real <- test_battery_continuous(real_data[[question_id]], question_id, "Real")
      synthetic <- test_battery_continuous(synthetic_data[[question_id]], question_id, "Synthetic")
      comparison <- continuous_question_test(real, synthetic, margin, alpha, confidence_level)
    } else if (question_type == "binary") {
      real <- test_battery_discrete(real_data[[question_id]], question_id, "Real")
      synthetic <- test_battery_discrete(synthetic_data[[question_id]], question_id, "Synthetic")
      comparison <- binary_question_test(
        real,
        synthetic,
        question$positive_level[[1L]],
        margin,
        alpha,
        confidence_level
      )
    } else {
      real <- test_battery_discrete(real_data[[question_id]], question_id, "Real")
      synthetic <- test_battery_discrete(synthetic_data[[question_id]], question_id, "Synthetic")
      comparison <- categorical_question_test(
        real,
        synthetic,
        margin,
        alpha,
        confidence_level,
        as.integer(bootstrap_replicates),
        as.integer(seed) + index - 1L
      )
    }
    result_rows[[index]] <- test_battery_result_row(
      question,
      comparison,
      confidence_level,
      length(real),
      length(synthetic)
    )
    tost_rows[[index]] <- test_battery_tost_rows(question, comparison)
  }

  results <- do.call(rbind, result_rows)
  equivalence <- do.call(rbind, tost_rows)
  rownames(results) <- NULL
  rownames(equivalence) <- NULL
  stopifnot(
    all(is.finite(results$effect_estimate)),
    all(is.finite(results$confidence_lower)),
    all(is.finite(results$confidence_upper)),
    all(is.finite(equivalence$effect_estimate)),
    all(is.finite(equivalence$confidence_lower)),
    all(is.finite(equivalence$confidence_upper))
  )

  list(
    results = results,
    equivalence = equivalence,
    registry = registry,
    alpha = alpha,
    confidence_level = confidence_level,
    bootstrap_replicates = as.integer(bootstrap_replicates),
    seed = as.integer(seed)
  )
}
