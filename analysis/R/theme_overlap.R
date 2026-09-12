THEME_OVERLAP_SAMPLES <- c("real", "synthetic")

theme_overlap_require_columns <- function(frame, columns, label) {
  if (!is.data.frame(frame)) {
    stop(sprintf("%s must be a data frame.", label))
  }
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

theme_overlap_non_blank <- function(values, label, unique_values = FALSE) {
  normalized <- trimws(as.character(values))
  if (length(normalized) == 0L || any(is.na(values)) || any(normalized == "")) {
    stop(sprintf("%s must be present and non-blank.", label))
  }
  if (unique_values && anyDuplicated(normalized)) {
    stop(sprintf("%s must be unique.", label))
  }
  normalized
}

validate_theme_codebook <- function(codebook) {
  theme_overlap_require_columns(
    codebook,
    c("theme_id", "label", "definition"),
    "Theme codebook"
  )
  if (nrow(codebook) == 0L) {
    stop("Theme codebook must contain at least one pre-registered theme.")
  }

  data.frame(
    theme_id = theme_overlap_non_blank(codebook$theme_id, "Theme codebook theme_id values", TRUE),
    label = theme_overlap_non_blank(codebook$label, "Theme codebook labels", TRUE),
    definition = theme_overlap_non_blank(codebook$definition, "Theme codebook definitions"),
    stringsAsFactors = FALSE
  )
}

validate_theme_texts <- function(frame, id_column, text_column, label) {
  if (length(id_column) != 1L || is.na(id_column) || !nzchar(trimws(id_column)) ||
      length(text_column) != 1L || is.na(text_column) || !nzchar(trimws(text_column))) {
    stop(sprintf("%s ID and text columns must each name exactly one column.", label))
  }
  if (identical(id_column, text_column)) {
    stop(sprintf("%s ID and text columns must be different.", label))
  }
  theme_overlap_require_columns(frame, c(id_column, text_column), label)
  if (nrow(frame) == 0L) {
    stop(sprintf("%s must contain at least one response.", label))
  }

  ids <- theme_overlap_non_blank(frame[[id_column]], sprintf("%s response IDs", label), TRUE)
  theme_overlap_non_blank(frame[[text_column]], sprintf("%s text", label))
  ids
}

validate_theme_judges <- function(judge_models) {
  judges <- theme_overlap_non_blank(judge_models, "Judge model IDs", TRUE)
  if (length(judges) != 2L) {
    stop("Theme coding requires exactly two distinct judge models.")
  }
  judges
}

normalize_theme_presence <- function(values) {
  if (is.logical(values)) {
    if (any(is.na(values))) {
      stop("Judge coding present values must be complete TRUE/FALSE or 1/0 decisions.")
    }
    return(values)
  }

  normalized <- trimws(as.character(values))
  if (any(is.na(values)) || any(!normalized %in% c("0", "1"))) {
    stop("Judge coding present values must be complete TRUE/FALSE or 1/0 decisions.")
  }
  normalized == "1"
}

theme_overlap_expected_keys <- function(judges, real_ids, synthetic_ids, theme_ids) {
  responses <- rbind(
    data.frame(sample = "real", response_id = real_ids, stringsAsFactors = FALSE),
    data.frame(sample = "synthetic", response_id = synthetic_ids, stringsAsFactors = FALSE)
  )
  expected <- merge(
    merge(
      data.frame(judge_model = judges, stringsAsFactors = FALSE),
      responses,
      all = TRUE
    ),
    data.frame(theme_id = theme_ids, stringsAsFactors = FALSE),
    all = TRUE
  )
  expected[c("judge_model", "sample", "response_id", "theme_id")]
}

theme_overlap_key <- function(frame) {
  do.call(paste, c(frame[c("judge_model", "sample", "response_id", "theme_id")], sep = "\r"))
}

validate_theme_codings <- function(codings, judges, real_ids, synthetic_ids, theme_ids) {
  required <- c("judge_model", "sample", "response_id", "theme_id", "present")
  theme_overlap_require_columns(codings, required, "Judge codings")
  normalized <- data.frame(
    judge_model = theme_overlap_non_blank(codings$judge_model, "Judge coding model IDs"),
    sample = tolower(theme_overlap_non_blank(codings$sample, "Judge coding sample values")),
    response_id = theme_overlap_non_blank(codings$response_id, "Judge coding response IDs"),
    theme_id = theme_overlap_non_blank(codings$theme_id, "Judge coding theme IDs"),
    present = normalize_theme_presence(codings$present),
    stringsAsFactors = FALSE
  )

  unsupported_judges <- setdiff(unique(normalized$judge_model), judges)
  if (length(unsupported_judges) > 0L) {
    stop(sprintf(
      "Judge codings contain models outside the two registered judges: %s",
      paste(unsupported_judges, collapse = ", ")
    ))
  }
  unsupported_samples <- setdiff(unique(normalized$sample), THEME_OVERLAP_SAMPLES)
  if (length(unsupported_samples) > 0L) {
    stop(sprintf(
      "Judge codings contain unsupported sample values: %s",
      paste(unsupported_samples, collapse = ", ")
    ))
  }
  unsupported_themes <- setdiff(unique(normalized$theme_id), theme_ids)
  if (length(unsupported_themes) > 0L) {
    stop(sprintf(
      "Judge codings contain themes outside the fixed codebook: %s",
      paste(unsupported_themes, collapse = ", ")
    ))
  }

  real_unknown <- setdiff(
    unique(normalized$response_id[normalized$sample == "real"]),
    real_ids
  )
  synthetic_unknown <- setdiff(
    unique(normalized$response_id[normalized$sample == "synthetic"]),
    synthetic_ids
  )
  if (length(real_unknown) > 0L || length(synthetic_unknown) > 0L) {
    stop(sprintf(
      "Judge codings contain response IDs outside their declared sample: %s",
      paste(c(real_unknown, synthetic_unknown), collapse = ", ")
    ))
  }

  keys <- theme_overlap_key(normalized)
  if (anyDuplicated(keys)) {
    stop("Judge codings must contain each judge/sample/response/theme decision exactly once; duplicates found.")
  }
  expected <- theme_overlap_expected_keys(judges, real_ids, synthetic_ids, theme_ids)
  expected_keys <- theme_overlap_key(expected)
  missing_keys <- setdiff(expected_keys, keys)
  unexpected_keys <- setdiff(keys, expected_keys)
  if (length(missing_keys) > 0L || length(unexpected_keys) > 0L) {
    stop(sprintf(
      paste(
        "Judge codings must be a complete independent coding grid for both judges;",
        "found %d missing and %d unexpected decisions."
      ),
      length(missing_keys),
      length(unexpected_keys)
    ))
  }

  order_index <- match(expected_keys, keys)
  normalized <- normalized[order_index, , drop = FALSE]
  rownames(normalized) <- NULL
  normalized
}

extract_theme_codings <- function(judge_coder, judges, real_responses, synthetic_responses, codebook) {
  if (!is.function(judge_coder)) {
    stop("judge_coder must be a function that independently codes each model and sample.")
  }

  samples <- list(real = real_responses, synthetic = synthetic_responses)
  batches <- unlist(lapply(judges, function(judge) {
    lapply(names(samples), function(sample) {
      decisions <- tryCatch(
        judge_coder(
          judge_model = judge,
          sample = sample,
          responses = samples[[sample]],
          codebook = codebook
        ),
        error = function(error) {
          stop(sprintf(
            "Theme judge %s failed while coding the %s sample: %s",
            judge,
            sample,
            conditionMessage(error)
          ), call. = FALSE)
        }
      )
      theme_overlap_require_columns(
        decisions,
        c("response_id", "theme_id", "present"),
        sprintf("Theme judge %s %s decisions", judge, sample)
      )
      data.frame(
        judge_model = rep(judge, nrow(decisions)),
        sample = rep(sample, nrow(decisions)),
        response_id = decisions$response_id,
        theme_id = decisions$theme_id,
        present = decisions$present,
        stringsAsFactors = FALSE
      )
    })
  }), recursive = FALSE)
  do.call(rbind, batches)
}

cohens_kappa <- function(first_rater, second_rater) {
  if (length(first_rater) != length(second_rater) || length(first_rater) == 0L) {
    stop("Cohen's kappa requires two non-empty rating vectors of equal length.")
  }
  first <- normalize_theme_presence(first_rater)
  second <- normalize_theme_presence(second_rater)
  observed <- mean(first == second)
  first_positive <- mean(first)
  second_positive <- mean(second)
  expected <- first_positive * second_positive +
    (1 - first_positive) * (1 - second_positive)
  denominator <- 1 - expected

  if (abs(denominator) <= .Machine$double.eps^0.5) {
    return(c(
      observed_agreement = observed,
      expected_agreement = expected,
      cohens_kappa = NA_real_
    ))
  }
  c(
    observed_agreement = observed,
    expected_agreement = expected,
    cohens_kappa = (observed - expected) / denominator
  )
}

theme_agreement_report <- function(codings, judges, theme_ids) {
  agreement_for <- function(rows, theme_id) {
    first <- rows$present[rows$judge_model == judges[[1L]]]
    second <- rows$present[rows$judge_model == judges[[2L]]]
    statistics <- cohens_kappa(first, second)
    data.frame(
      theme_id = theme_id,
      rated_units = length(first),
      observed_agreement = unname(statistics[["observed_agreement"]]),
      expected_agreement = unname(statistics[["expected_agreement"]]),
      cohens_kappa = unname(statistics[["cohens_kappa"]]),
      status = if (is.na(statistics[["cohens_kappa"]])) {
        "undefined_no_expected_disagreement"
      } else {
        "estimated"
      },
      stringsAsFactors = FALSE
    )
  }

  rows <- lapply(theme_ids, function(theme_id) {
    agreement_for(codings[codings$theme_id == theme_id, , drop = FALSE], theme_id)
  })
  rows[[length(rows) + 1L]] <- agreement_for(codings, "__overall__")
  do.call(rbind, rows)
}

theme_prevalence_report <- function(codings, judges, theme_ids) {
  rows <- lapply(judges, function(judge) {
    lapply(theme_ids, function(theme_id) {
      selected <- codings$judge_model == judge & codings$theme_id == theme_id
      real <- codings$present[selected & codings$sample == "real"]
      synthetic <- codings$present[selected & codings$sample == "synthetic"]
      data.frame(
        judge_model = judge,
        theme_id = theme_id,
        real_prevalence = mean(real),
        synthetic_prevalence = mean(synthetic),
        prevalence_intersection = min(mean(real), mean(synthetic)),
        prevalence_union = max(mean(real), mean(synthetic)),
        prevalence_similarity = 1 - abs(mean(real) - mean(synthetic)),
        stringsAsFactors = FALSE
      )
    })
  })
  do.call(rbind, unlist(rows, recursive = FALSE))
}

theme_overlap_score <- function(real_prevalence, synthetic_prevalence) {
  if (length(real_prevalence) != length(synthetic_prevalence) ||
      length(real_prevalence) == 0L ||
      any(!is.finite(real_prevalence)) || any(!is.finite(synthetic_prevalence)) ||
      any(real_prevalence < 0 | real_prevalence > 1) ||
      any(synthetic_prevalence < 0 | synthetic_prevalence > 1)) {
    stop("Theme overlap requires equal, non-empty prevalence vectors bounded by zero and one.")
  }
  intersection <- sum(pmin(real_prevalence, synthetic_prevalence))
  union <- sum(pmax(real_prevalence, synthetic_prevalence))
  real_set <- real_prevalence > 0
  synthetic_set <- synthetic_prevalence > 0
  observed_themes <- real_set | synthetic_set
  set_union <- sum(real_set | synthetic_set)
  prevalence_similarity <- 1 - abs(real_prevalence - synthetic_prevalence)

  c(
    weighted_jaccard = if (union == 0) NA_real_ else intersection / union,
    set_jaccard = if (set_union == 0L) NA_real_ else sum(real_set & synthetic_set) / set_union,
    mean_prevalence_similarity = if (any(observed_themes)) {
      mean(prevalence_similarity[observed_themes])
    } else {
      NA_real_
    }
  )
}

theme_overlap_report <- function(prevalence, judges, theme_ids) {
  pooled <- do.call(rbind, lapply(theme_ids, function(theme_id) {
    rows <- prevalence[prevalence$theme_id == theme_id, , drop = FALSE]
    real <- mean(rows$real_prevalence)
    synthetic <- mean(rows$synthetic_prevalence)
    data.frame(
      theme_id = theme_id,
      real_prevalence = real,
      synthetic_prevalence = synthetic,
      prevalence_intersection = min(real, synthetic),
      prevalence_union = max(real, synthetic),
      prevalence_similarity = 1 - abs(real - synthetic),
      stringsAsFactors = FALSE
    )
  }))

  summary_rows <- lapply(judges, function(judge) {
    rows <- prevalence[prevalence$judge_model == judge, , drop = FALSE]
    scores <- theme_overlap_score(rows$real_prevalence, rows$synthetic_prevalence)
    data.frame(
      judge_model = judge,
      weighted_jaccard = unname(scores[["weighted_jaccard"]]),
      set_jaccard = unname(scores[["set_jaccard"]]),
      mean_prevalence_similarity = unname(scores[["mean_prevalence_similarity"]]),
      stringsAsFactors = FALSE
    )
  })
  pooled_scores <- theme_overlap_score(pooled$real_prevalence, pooled$synthetic_prevalence)
  summary_rows[[length(summary_rows) + 1L]] <- data.frame(
    judge_model = "__pooled__",
    weighted_jaccard = unname(pooled_scores[["weighted_jaccard"]]),
    set_jaccard = unname(pooled_scores[["set_jaccard"]]),
    mean_prevalence_similarity = unname(pooled_scores[["mean_prevalence_similarity"]]),
    stringsAsFactors = FALSE
  )

  list(per_theme = pooled, summary = do.call(rbind, summary_rows))
}

run_theme_overlap <- function(
  real_verbatims,
  synthetic_answers,
  codebook,
  judge_models,
  judge_coder,
  real_id_column = "response_id",
  real_text_column = "text",
  synthetic_id_column = "response_id",
  synthetic_text_column = "text"
) {
  fixed_codebook <- validate_theme_codebook(codebook)
  judges <- validate_theme_judges(judge_models)
  real_ids <- validate_theme_texts(
    real_verbatims,
    real_id_column,
    real_text_column,
    "Real verbatims"
  )
  synthetic_ids <- validate_theme_texts(
    synthetic_answers,
    synthetic_id_column,
    synthetic_text_column,
    "Synthetic interview answers"
  )
  real_responses <- data.frame(
    response_id = real_ids,
    text = trimws(as.character(real_verbatims[[real_text_column]])),
    stringsAsFactors = FALSE
  )
  synthetic_responses <- data.frame(
    response_id = synthetic_ids,
    text = trimws(as.character(synthetic_answers[[synthetic_text_column]])),
    stringsAsFactors = FALSE
  )
  extracted_codings <- extract_theme_codings(
    judge_coder,
    judges,
    real_responses,
    synthetic_responses,
    fixed_codebook
  )
  codings <- validate_theme_codings(
    extracted_codings,
    judges,
    real_ids,
    synthetic_ids,
    fixed_codebook$theme_id
  )
  prevalence <- theme_prevalence_report(codings, judges, fixed_codebook$theme_id)
  overlap <- theme_overlap_report(prevalence, judges, fixed_codebook$theme_id)
  agreement <- theme_agreement_report(codings, judges, fixed_codebook$theme_id)

  structure(
    list(
      codebook = fixed_codebook,
      judges = data.frame(
        judge_order = seq_along(judges),
        model_id = judges,
        stringsAsFactors = FALSE
      ),
      codings = codings,
      theme_prevalence_by_judge = prevalence,
      theme_overlap = overlap$per_theme,
      overlap_summary = overlap$summary,
      agreement = agreement,
      audit = data.frame(
        real_response_count = length(real_ids),
        synthetic_response_count = length(synthetic_ids),
        judge_count = length(judges),
        judge_invocation_count = length(judges) * length(THEME_OVERLAP_SAMPLES),
        coding_decision_count = nrow(codings),
        coding_mode = "independent_judge_coder_fixed_codebook",
        verbatim_text_returned = FALSE,
        stringsAsFactors = FALSE
      )
    ),
    class = c("theme_overlap_result", "list")
  )
}

print.theme_overlap_result <- function(x, ...) {
  overall_agreement <- x$agreement[x$agreement$theme_id == "__overall__", , drop = FALSE]
  pooled_overlap <- x$overlap_summary[
    x$overlap_summary$judge_model == "__pooled__",
    ,
    drop = FALSE
  ]
  cat("Theme overlap validation\n")
  cat(sprintf("Judge models: %s\n", paste(x$judges$model_id, collapse = " | ")))
  if (is.na(pooled_overlap$weighted_jaccard)) {
    cat("Pooled prevalence-weighted Jaccard overlap: undefined (no observed themes)\n")
  } else {
    cat(sprintf("Pooled prevalence-weighted Jaccard overlap: %.3f\n", pooled_overlap$weighted_jaccard))
  }
  if (is.na(overall_agreement$cohens_kappa)) {
    cat("Cohen's kappa: undefined (no expected disagreement)\n")
  } else {
    cat(sprintf("Cohen's kappa: %.3f\n", overall_agreement$cohens_kappa))
  }
  invisible(x)
}
