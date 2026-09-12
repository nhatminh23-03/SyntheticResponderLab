NON_LLM_BASELINES <- c(
  "marginal_sampler",
  "multivariate_normal",
  "gaussian_copula",
  "stratum_mean",
  "knn_lookup"
)

as_id <- function(values, label) {
  ids <- trimws(as.character(values))
  if (any(is.na(values)) || any(ids == "") || anyDuplicated(ids)) {
    stop(sprintf("%s must be present and unique.", label))
  }
  ids
}

require_named_columns <- function(frame, columns, label) {
  if (length(columns) == 0L || any(is.na(columns)) || any(columns == "") || anyDuplicated(columns)) {
    stop(sprintf("%s must name one or more unique columns.", label))
  }
  missing <- setdiff(columns, names(frame))
  if (length(missing) > 0L) {
    stop(sprintf("Missing %s: %s", label, paste(missing, collapse = ", ")))
  }
}

validate_baseline_data <- function(
  data,
  id_column,
  item_columns,
  stratum_columns,
  knn_columns,
  expected_rows = 600L,
  expected_items = 32L
) {
  if (!is.data.frame(data)) {
    stop("Baseline input must be a data frame.")
  }
  if (nrow(data) != expected_rows) {
    stop(sprintf("Expected exactly %d real respondents; found %d.", expected_rows, nrow(data)))
  }
  if (length(item_columns) != expected_items) {
    stop(sprintf("Expected exactly %d instrument item columns; found %d.", expected_items, length(item_columns)))
  }

  require_named_columns(data, id_column, "respondent ID column")
  if (length(id_column) != 1L) {
    stop("Respondent ID must name exactly one column.")
  }
  require_named_columns(data, item_columns, "instrument item columns")
  require_named_columns(data, stratum_columns, "stratum columns")
  require_named_columns(data, knn_columns, "k-NN demographic columns")

  overlap <- intersect(item_columns, unique(c(id_column, stratum_columns, knn_columns)))
  if (length(overlap) > 0L) {
    stop(sprintf(
      "Instrument items cannot also be IDs or demographic predictors: %s",
      paste(overlap, collapse = ", ")
    ))
  }

  as_id(data[[id_column]], "Respondent IDs")
  non_numeric <- item_columns[!vapply(data[item_columns], is.numeric, logical(1L))]
  if (length(non_numeric) > 0L) {
    stop(sprintf("Instrument items must be numeric: %s", paste(non_numeric, collapse = ", ")))
  }
  non_finite <- item_columns[vapply(data[item_columns], function(values) {
    any(!is.finite(values))
  }, logical(1L))]
  if (length(non_finite) > 0L) {
    stop(sprintf("Instrument items must be complete and finite: %s", paste(non_finite, collapse = ", ")))
  }

  invisible(TRUE)
}

assert_held_out <- function(fit_ids, evaluation_ids) {
  fit_ids <- as_id(fit_ids, "Fit respondent IDs")
  evaluation_ids <- as_id(evaluation_ids, "Evaluation respondent IDs")
  overlap <- intersect(fit_ids, evaluation_ids)
  if (length(overlap) > 0L) {
    stop(sprintf(
      "Held-out violation: %d respondent ID(s) occur in both fit and evaluation rows.",
      length(overlap)
    ))
  }
  invisible(TRUE)
}

held_out_split <- function(respondent_ids, seed = 20260904L) {
  respondent_ids <- as_id(respondent_ids, "Respondent IDs")
  respondent_n <- length(respondent_ids)
  if (respondent_n %% 2L != 0L) {
    stop("The held-out split requires an even number of respondents.")
  }

  set.seed(seed)
  fit_index <- sort(sample.int(respondent_n, respondent_n / 2L, replace = FALSE))
  evaluation_index <- setdiff(seq_len(respondent_n), fit_index)
  assert_held_out(respondent_ids[fit_index], respondent_ids[evaluation_index])

  list(
    seed = as.integer(seed),
    fit_index = fit_index,
    evaluation_index = evaluation_index,
    fit_ids = respondent_ids[fit_index],
    evaluation_ids = respondent_ids[evaluation_index]
  )
}

matrix_square_root <- function(covariance) {
  covariance <- (covariance + t(covariance)) / 2
  decomposition <- eigen(covariance, symmetric = TRUE)
  values <- pmax(decomposition$values, 0)
  decomposition$vectors %*% diag(sqrt(values), nrow = length(values))
}

draw_gaussian <- function(n, covariance) {
  if (length(n) != 1L || is.na(n) || n < 1L || n != as.integer(n)) {
    stop("Prediction row count must be a positive integer.")
  }
  dimensions <- ncol(covariance)
  independent <- matrix(stats::rnorm(n * dimensions), nrow = n, ncol = dimensions)
  independent %*% t(matrix_square_root(covariance))
}

standardized_covariance <- function(values) {
  means <- colMeans(values)
  standard_deviations <- apply(values, 2L, stats::sd)
  safe_deviations <- ifelse(standard_deviations > 0, standard_deviations, 1)
  standardized <- sweep(sweep(values, 2L, means, "-"), 2L, safe_deviations, "/")
  covariance <- crossprod(standardized) / (nrow(standardized) - 1L)
  dimnames(covariance) <- list(colnames(values), colnames(values))

  list(
    means = means,
    standard_deviations = standard_deviations,
    covariance = covariance
  )
}

new_baseline_fit <- function(method, item_columns, fit_ids, model) {
  structure(
    c(list(method = method, item_columns = item_columns, fit_ids = fit_ids), model),
    class = c("non_llm_baseline_fit", "list")
  )
}

fit_marginal_sampler <- function(fit_data, item_columns, fit_ids) {
  new_baseline_fit(
    "marginal_sampler",
    item_columns,
    fit_ids,
    list(marginals = lapply(fit_data[item_columns], identity))
  )
}

fit_multivariate_normal <- function(fit_data, item_columns, fit_ids) {
  item_matrix <- as.matrix(fit_data[item_columns])
  moments <- standardized_covariance(item_matrix)
  new_baseline_fit("multivariate_normal", item_columns, fit_ids, moments)
}

fit_gaussian_copula <- function(fit_data, item_columns, fit_ids) {
  item_matrix <- as.matrix(fit_data[item_columns])
  row_n <- nrow(item_matrix)
  latent <- apply(item_matrix, 2L, function(values) {
    stats::qnorm(rank(values, ties.method = "average") / (row_n + 1))
  })
  latent_moments <- standardized_covariance(latent)

  new_baseline_fit(
    "gaussian_copula",
    item_columns,
    fit_ids,
    list(
      latent_covariance = latent_moments$covariance,
      marginals = lapply(fit_data[item_columns], sort)
    )
  )
}

stratum_key <- function(data, columns) {
  encoded <- lapply(data[columns], function(values) {
    values <- as.character(values)
    values[is.na(values)] <- "<missing>"
    paste0(nchar(values, type = "bytes"), ":", values)
  })
  do.call(paste, c(encoded, sep = "|"))
}

fit_stratum_mean <- function(fit_data, item_columns, fit_ids, stratum_columns) {
  keys <- stratum_key(fit_data, stratum_columns)
  unique_keys <- unique(keys)
  group_means <- t(vapply(unique_keys, function(key) {
    colMeans(fit_data[keys == key, item_columns, drop = FALSE])
  }, numeric(length(item_columns))))
  colnames(group_means) <- item_columns
  rownames(group_means) <- unique_keys

  new_baseline_fit(
    "stratum_mean",
    item_columns,
    fit_ids,
    list(
      stratum_columns = stratum_columns,
      group_means = group_means,
      overall_means = colMeans(fit_data[item_columns])
    )
  )
}

fit_demographic_encoder <- function(data, columns) {
  specifications <- lapply(columns, function(column) {
    values <- data[[column]]
    if (is.numeric(values)) {
      center <- mean(values, na.rm = TRUE)
      if (!is.finite(center)) {
        stop(sprintf("Numeric k-NN column %s has no finite training values.", column))
      }
      scale <- stats::sd(values, na.rm = TRUE)
      if (!is.finite(scale) || scale == 0) {
        scale <- 1
      }
      list(column = column, type = "numeric", center = center, scale = scale)
    } else {
      normalized <- as.character(values)
      normalized[is.na(normalized)] <- "<missing>"
      list(column = column, type = "categorical", levels = sort(unique(normalized)))
    }
  })
  names(specifications) <- columns
  specifications
}

encode_demographics <- function(data, specifications) {
  blocks <- lapply(specifications, function(specification) {
    values <- data[[specification$column]]
    if (identical(specification$type, "numeric")) {
      values <- as.numeric(values)
      values[!is.finite(values)] <- specification$center
      return(matrix(
        (values - specification$center) / specification$scale,
        ncol = 1L,
        dimnames = list(NULL, specification$column)
      ))
    }

    values <- as.character(values)
    values[is.na(values)] <- "<missing>"
    block <- vapply(specification$levels, function(level) {
      as.numeric(values == level)
    }, numeric(nrow(data)))
    matrix(
      block,
      nrow = nrow(data),
      ncol = length(specification$levels),
      dimnames = list(NULL, paste(specification$column, specification$levels, sep = "="))
    )
  })
  do.call(cbind, blocks)
}

fit_knn_lookup <- function(fit_data, item_columns, fit_ids, knn_columns, k = 5L) {
  if (length(k) != 1L || is.na(k) || k < 1L || k != as.integer(k)) {
    stop("k must be a positive integer.")
  }
  if (nrow(fit_data) < k) {
    stop(sprintf("k-NN needs at least k=%d fit rows; found %d.", k, nrow(fit_data)))
  }
  encoder <- fit_demographic_encoder(fit_data, knn_columns)
  new_baseline_fit(
    "knn_lookup",
    item_columns,
    fit_ids,
    list(
      knn_columns = knn_columns,
      k = as.integer(k),
      encoder = encoder,
      fit_demographics = encode_demographics(fit_data, encoder),
      fit_answers = as.matrix(fit_data[item_columns])
    )
  )
}

fit_non_llm_baselines <- function(
  fit_data,
  id_column,
  item_columns,
  stratum_columns,
  knn_columns,
  k = 5L
) {
  fit_ids <- as_id(fit_data[[id_column]], "Fit respondent IDs")
  list(
    marginal_sampler = fit_marginal_sampler(fit_data, item_columns, fit_ids),
    multivariate_normal = fit_multivariate_normal(fit_data, item_columns, fit_ids),
    gaussian_copula = fit_gaussian_copula(fit_data, item_columns, fit_ids),
    stratum_mean = fit_stratum_mean(fit_data, item_columns, fit_ids, stratum_columns),
    knn_lookup = fit_knn_lookup(fit_data, item_columns, fit_ids, knn_columns, k)
  )
}

empirical_inverse <- function(sorted_values, probabilities) {
  indexes <- ceiling(probabilities * length(sorted_values))
  indexes <- pmax(1L, pmin(length(sorted_values), indexes))
  sorted_values[indexes]
}

predict_non_llm_baseline <- function(fit, new_data, id_column, seed = 20260904L) {
  if (!inherits(fit, "non_llm_baseline_fit")) {
    stop("fit must be a non-LLM baseline fit.")
  }
  require_named_columns(new_data, id_column, "evaluation respondent ID column")
  evaluation_ids <- as_id(new_data[[id_column]], "Evaluation respondent IDs")
  assert_held_out(fit$fit_ids, evaluation_ids)
  row_n <- nrow(new_data)
  item_columns <- fit$item_columns
  set.seed(seed)

  answers <- switch(
    fit$method,
    marginal_sampler = {
      matrix(vapply(fit$marginals, function(values) {
        values[sample.int(length(values), row_n, replace = TRUE)]
      }, numeric(row_n)), nrow = row_n, dimnames = list(NULL, item_columns))
    },
    multivariate_normal = {
      standardized <- draw_gaussian(row_n, fit$covariance)
      shifted <- sweep(standardized, 2L, fit$standard_deviations, "*")
      sweep(shifted, 2L, fit$means, "+")
    },
    gaussian_copula = {
      latent <- draw_gaussian(row_n, fit$latent_covariance)
      probabilities <- stats::pnorm(latent)
      matrix(vapply(seq_along(item_columns), function(index) {
        empirical_inverse(fit$marginals[[index]], probabilities[, index])
      }, numeric(row_n)), nrow = row_n, dimnames = list(NULL, item_columns))
    },
    stratum_mean = {
      require_named_columns(new_data, fit$stratum_columns, "evaluation stratum columns")
      keys <- stratum_key(new_data, fit$stratum_columns)
      matrix(vapply(keys, function(key) {
        if (key %in% rownames(fit$group_means)) {
          fit$group_means[key, ]
        } else {
          fit$overall_means
        }
      }, numeric(length(item_columns))), nrow = row_n, byrow = TRUE,
      dimnames = list(NULL, item_columns))
    },
    knn_lookup = {
      require_named_columns(new_data, fit$knn_columns, "evaluation k-NN demographic columns")
      evaluation_demographics <- encode_demographics(new_data, fit$encoder)
      matrix(vapply(seq_len(row_n), function(index) {
        differences <- sweep(fit$fit_demographics, 2L, evaluation_demographics[index, ], "-")
        distances <- sqrt(rowSums(differences^2))
        neighbours <- order(distances, seq_along(distances))[seq_len(fit$k)]
        colMeans(fit$fit_answers[neighbours, , drop = FALSE])
      }, numeric(length(item_columns))), nrow = row_n, byrow = TRUE,
      dimnames = list(NULL, item_columns))
    },
    stop(sprintf("Unknown non-LLM baseline method: %s", fit$method))
  )

  colnames(answers) <- item_columns
  output <- data.frame(evaluation_id = evaluation_ids, answers, check.names = FALSE)
  stopifnot(nrow(output) == row_n, identical(names(output)[-1L], item_columns))
  output
}

root_mean_square <- function(values) {
  sqrt(mean(values^2))
}

off_diagonal <- function(values) {
  values[row(values) != col(values)]
}

evaluate_baseline <- function(reference, prediction, item_columns) {
  reference <- as.matrix(reference[item_columns])
  prediction <- as.matrix(prediction[item_columns])
  if (!identical(dim(reference), dim(prediction))) {
    stop("Held-out reference and baseline prediction dimensions must match.")
  }

  reference_correlation <- suppressWarnings(stats::cor(reference))
  prediction_correlation <- suppressWarnings(stats::cor(prediction))
  correlation_differences <- off_diagonal(prediction_correlation - reference_correlation)
  correlations_are_complete <- length(correlation_differences) > 0L &&
    all(is.finite(correlation_differences))

  data.frame(
    mean_rmse = root_mean_square(colMeans(prediction) - colMeans(reference)),
    sd_rmse = root_mean_square(
      apply(prediction, 2L, stats::sd) - apply(reference, 2L, stats::sd)
    ),
    correlation_rmse = if (correlations_are_complete) {
      root_mean_square(correlation_differences)
    } else {
      NA_real_
    },
    stringsAsFactors = FALSE
  )
}

run_non_llm_baselines <- function(
  real_data,
  id_column,
  item_columns,
  stratum_columns,
  knn_columns,
  seed = 20260904L,
  k = 5L,
  expected_rows = 600L,
  expected_items = 32L
) {
  validate_baseline_data(
    real_data,
    id_column,
    item_columns,
    stratum_columns,
    knn_columns,
    expected_rows,
    expected_items
  )
  split <- held_out_split(real_data[[id_column]], seed)
  fit_data <- real_data[split$fit_index, , drop = FALSE]
  evaluation_data <- real_data[split$evaluation_index, , drop = FALSE]
  fits <- fit_non_llm_baselines(
    fit_data,
    id_column,
    item_columns,
    stratum_columns,
    knn_columns,
    k
  )

  evaluation_input_columns <- unique(c(id_column, stratum_columns, knn_columns))
  evaluation_inputs <- evaluation_data[evaluation_input_columns]
  predictions <- setNames(lapply(seq_along(fits), function(index) {
    predict_non_llm_baseline(fits[[index]], evaluation_inputs, id_column, seed + index)
  }), names(fits))

  metrics <- do.call(rbind, lapply(names(predictions), function(method) {
    data.frame(
      baseline = method,
      evaluate_baseline(evaluation_data, predictions[[method]], item_columns),
      stringsAsFactors = FALSE
    )
  }))
  rownames(metrics) <- NULL

  audit <- data.frame(
    baseline = names(fits),
    fit_rows = vapply(fits, function(fit) length(fit$fit_ids), integer(1L)),
    evaluation_rows = vapply(predictions, nrow, integer(1L)),
    overlap_rows = vapply(fits, function(fit) {
      length(intersect(fit$fit_ids, split$evaluation_ids))
    }, integer(1L)),
    stringsAsFactors = FALSE
  )
  stopifnot(
    identical(names(fits), NON_LLM_BASELINES),
    all(audit$fit_rows == expected_rows / 2L),
    all(audit$evaluation_rows == expected_rows / 2L),
    all(audit$overlap_rows == 0L)
  )

  list(
    split = split,
    fits = fits,
    predictions = predictions,
    metrics = metrics,
    audit = audit
  )
}
