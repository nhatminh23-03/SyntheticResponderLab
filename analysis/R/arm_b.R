ARM_B_DRAW_N <- 600L
ARM_B_SEED <- 20260904L
ARM_B_IPF_TOLERANCE <- 1e-10
ARM_B_IPF_MAX_ITERATIONS <- 1000L
ARM_B_BALANCED_DRAW_MAX_ATTEMPTS <- 1000L

ARM_B_AGE_LEVELS <- c("18-24", "25-34", "35-44", "45-54", "55-64", "65+")
ARM_B_GENDER_LEVELS <- c("Female", "Male")
ARM_B_INCOME_LEVELS <- c(
  "$0 - $24,999",
  "$25,000 - $49,999",
  "$50,000 - $74,999",
  "$75,000 - $99,999",
  "$100,000 - $199,999",
  "$200,000 or more"
)
ARM_B_STATE_BY_FIPS <- c(
  "1" = "Alabama", "2" = "Alaska", "4" = "Arizona", "5" = "Arkansas",
  "6" = "California", "8" = "Colorado", "9" = "Connecticut", "10" = "Delaware",
  "11" = "District of Columbia", "12" = "Florida", "13" = "Georgia", "15" = "Hawaii",
  "16" = "Idaho", "17" = "Illinois", "18" = "Indiana", "19" = "Iowa",
  "20" = "Kansas", "21" = "Kentucky", "22" = "Louisiana", "23" = "Maine",
  "24" = "Maryland", "25" = "Massachusetts", "26" = "Michigan", "27" = "Minnesota",
  "28" = "Mississippi", "29" = "Missouri", "30" = "Montana", "31" = "Nebraska",
  "32" = "Nevada", "33" = "New Hampshire", "34" = "New Jersey", "35" = "New Mexico",
  "36" = "New York", "37" = "North Carolina", "38" = "North Dakota", "39" = "Ohio",
  "40" = "Oklahoma", "41" = "Oregon", "42" = "Pennsylvania", "44" = "Rhode Island",
  "45" = "South Carolina", "46" = "South Dakota", "47" = "Tennessee", "48" = "Texas",
  "49" = "Utah", "50" = "Vermont", "51" = "Virginia", "53" = "Washington",
  "54" = "West Virginia", "55" = "Wisconsin", "56" = "Wyoming"
)

arm_b_require_columns <- function(frame, columns, label) {
  missing <- setdiff(columns, names(frame))
  if (length(missing) > 0L) {
    stop(sprintf("%s is missing required columns: %s", label, paste(missing, collapse = ", ")))
  }
}

arm_b_number <- function(values) {
  suppressWarnings(as.numeric(as.character(values)))
}

arm_b_age_band <- function(age) {
  cut(
    age,
    breaks = c(17, 24, 34, 44, 54, 64, Inf),
    labels = ARM_B_AGE_LEVELS,
    right = TRUE
  ) |>
    as.character()
}

arm_b_income_band <- function(income) {
  cut(
    income,
    breaks = c(-Inf, 24999, 49999, 74999, 99999, 199999, Inf),
    labels = ARM_B_INCOME_LEVELS,
    right = TRUE
  ) |>
    as.character()
}

arm_b_state_name <- function(state_fips) {
  numeric_state <- arm_b_number(state_fips)
  state <- unname(ARM_B_STATE_BY_FIPS[as.character(numeric_state)])
  state[!is.finite(numeric_state)] <- NA_character_
  state
}

arm_b_demographic_levels <- function() {
  list(
    age_band = ARM_B_AGE_LEVELS,
    gender = ARM_B_GENDER_LEVELS,
    income_band = ARM_B_INCOME_LEVELS,
    state = unname(ARM_B_STATE_BY_FIPS)
  )
}

read_arm_b_real_demographics <- function(path) {
  header <- utils::read.csv(path, nrows = 0L, check.names = FALSE, stringsAsFactors = FALSE)
  required <- c("Response ID", "Status", "Gender", "Age", "Household Income", "State")
  arm_b_require_columns(header, required, "real panel")
  column_classes <- rep("NULL", ncol(header))
  column_classes[match(required, names(header))] <- "character"
  utils::read.csv(
    path,
    check.names = FALSE,
    stringsAsFactors = FALSE,
    colClasses = column_classes
  )
}

harmonize_arm_b_real <- function(
  real_data,
  expected_rows = ARM_B_DRAW_N,
  id_column = "Response ID"
) {
  if (length(id_column) != 1L || is.na(id_column) || !nzchar(id_column)) {
    stop("Arm B real respondent ID must name exactly one non-empty column.")
  }
  arm_b_require_columns(
    real_data,
    c(id_column, "Status", "Gender", "Age", "Household Income", "State"),
    "real panel"
  )
  status <- trimws(as.character(real_data$Status))
  completed <- real_data[!is.na(status) & status == "Completed", , drop = FALSE]
  if (nrow(completed) != expected_rows) {
    stop(sprintf("Expected exactly %d completed real respondents; found %d.", expected_rows, nrow(completed)))
  }

  response_ids <- trimws(as.character(completed[[id_column]]))
  if (any(is.na(completed[[id_column]])) || any(response_ids == "") || anyDuplicated(response_ids)) {
    stop("Completed real respondent IDs must be present and unique.")
  }

  age <- arm_b_number(completed$Age)
  if (any(!is.finite(age)) || any(age < 18)) {
    stop("Completed real respondent ages must be complete, numeric, and at least 18.")
  }

  gender <- trimws(as.character(completed$Gender))
  if (any(is.na(completed$Gender)) || any(!gender %in% ARM_B_GENDER_LEVELS)) {
    stop("Completed real respondent gender must use the PUMS-harmonizable levels Female or Male.")
  }

  income_band <- trimws(as.character(completed[["Household Income"]]))
  unknown_income <- setdiff(unique(income_band), ARM_B_INCOME_LEVELS)
  if (length(unknown_income) > 0L || any(is.na(completed[["Household Income"]]))) {
    stop(sprintf(
      "Completed real respondent income contains unsupported levels: %s",
      paste(unknown_income, collapse = ", ")
    ))
  }

  state <- trimws(as.character(completed$State))
  unknown_state <- setdiff(unique(state), unname(ARM_B_STATE_BY_FIPS))
  if (length(unknown_state) > 0L || any(is.na(completed$State))) {
    stop(sprintf(
      "Completed real respondent state contains unsupported levels: %s",
      paste(unknown_state, collapse = ", ")
    ))
  }

  data.frame(
    age = age,
    age_band = arm_b_age_band(age),
    gender = gender,
    income_band = income_band,
    state = state,
    stringsAsFactors = FALSE
  )
}

arm_b_funnel_row <- function(stage, frame, weight_column = NULL) {
  weighted_households <- NA_real_
  if (!is.null(weight_column)) {
    weighted_households <- sum(arm_b_number(frame[[weight_column]]), na.rm = TRUE)
  }
  data.frame(
    stage = stage,
    records = nrow(frame),
    weighted_households = weighted_households,
    stringsAsFactors = FALSE
  )
}

build_arm_b_pums_frame <- function(housing, person) {
  arm_b_require_columns(
    housing,
    c("SERIALNO", "ST", "WGTP", "TEN", "HINCP", "ADJINC"),
    "Arm B housing PUMS frame"
  )
  arm_b_require_columns(
    person,
    c("SERIALNO", "ST", "RELSHIPP", "AGEP", "SEX"),
    "Arm B person PUMS frame"
  )
  if (anyDuplicated(housing$SERIALNO)) {
    stop("Arm B housing PUMS SERIALNO must be unique for the one-to-one join.")
  }

  rows <- list(arm_b_funnel_row("raw housing records", housing, "WGTP"))
  occupied <- housing[!is.na(arm_b_number(housing$TEN)), , drop = FALSE]
  rows[[length(rows) + 1L]] <- arm_b_funnel_row("occupied housing units", occupied, "WGTP")

  reference <- person[
    !is.na(arm_b_number(person$RELSHIPP)) & arm_b_number(person$RELSHIPP) == 20,
    c("SERIALNO", "ST", "AGEP", "SEX"),
    drop = FALSE
  ]
  if (anyDuplicated(reference$SERIALNO)) {
    stop("Arm B householder SERIALNO must be unique for the one-to-one join.")
  }

  joined <- merge(
    occupied,
    reference,
    by = "SERIALNO",
    all = FALSE,
    sort = FALSE,
    suffixes = c("_housing", "_person")
  )
  rows[[length(rows) + 1L]] <- arm_b_funnel_row("joined to householder record", joined, "WGTP")

  housing_state <- arm_b_number(joined$ST_housing)
  person_state <- arm_b_number(joined$ST_person)
  if (any(!is.finite(housing_state)) || any(!is.finite(person_state)) ||
      any(housing_state != person_state)) {
    stop("Arm B housing and person PUMS state codes must be present and agree after joining.")
  }

  age <- arm_b_number(joined$AGEP)
  income <- arm_b_number(joined$HINCP) * arm_b_number(joined$ADJINC) / 1000000
  sex <- arm_b_number(joined$SEX)
  weight <- arm_b_number(joined$WGTP)
  state <- arm_b_state_name(housing_state)
  complete <- is.finite(age) & age >= 18 & is.finite(income) &
    is.finite(sex) & sex %in% c(1, 2) & is.finite(weight) & weight > 0 & !is.na(state)
  eligible <- joined[complete, , drop = FALSE]
  rows[[length(rows) + 1L]] <- arm_b_funnel_row(
    "adult householders with complete demographics and positive WGTP",
    eligible,
    "WGTP"
  )
  if (nrow(eligible) == 0L) {
    stop("Arm B PUMS frame has no eligible adult householders with complete demographics.")
  }

  frame <- data.frame(
    donor_id = trimws(as.character(eligible$SERIALNO)),
    age = age[complete],
    age_band = arm_b_age_band(age[complete]),
    gender = ifelse(sex[complete] == 1, "Male", "Female"),
    household_income = income[complete],
    income_band = arm_b_income_band(income[complete]),
    state = arm_b_state_name(housing_state[complete]),
    base_weight = weight[complete],
    stringsAsFactors = FALSE
  )
  if (any(frame$donor_id == "") || anyDuplicated(frame$donor_id)) {
    stop("Arm B eligible PUMS donor IDs must be present and unique.")
  }
  if (anyNA(frame[, c("age_band", "gender", "income_band", "state")])) {
    stop("Arm B PUMS demographic harmonization produced missing match values.")
  }

  list(frame = frame, audit = do.call(rbind, rows))
}

arm_b_targets <- function(real) {
  levels <- arm_b_demographic_levels()
  lapply(names(levels), function(characteristic) {
    counts <- as.numeric(table(factor(real[[characteristic]], levels = levels[[characteristic]])))
    stats::setNames(counts / nrow(real), levels[[characteristic]])
  }) |>
    stats::setNames(names(levels))
}

arm_b_validate_ipf_inputs <- function(frame, targets, base_weights) {
  if (!is.list(targets) || length(targets) == 0L || is.null(names(targets)) || any(names(targets) == "")) {
    stop("Arm B IPF targets must be a named, non-empty list of margins.")
  }
  arm_b_require_columns(frame, names(targets), "Arm B IPF frame")
  if (length(base_weights) != nrow(frame) || any(!is.finite(base_weights)) || any(base_weights <= 0)) {
    stop("Arm B IPF base weights must be finite, positive, and have one value per PUMS row.")
  }

  for (characteristic in names(targets)) {
    target <- targets[[characteristic]]
    if (is.null(names(target)) || any(names(target) == "") || anyDuplicated(names(target)) ||
        any(!is.finite(target)) || any(target < 0) || sum(target) <= 0) {
      stop(sprintf("Arm B IPF target margin %s is invalid.", characteristic))
    }
    values <- as.character(frame[[characteristic]])
    unknown <- setdiff(unique(values), names(target))
    if (length(unknown) > 0L || anyNA(values)) {
      stop(sprintf("Arm B IPF frame contains unsupported %s levels.", characteristic))
    }
    available <- vapply(names(target), function(level) any(values == level), logical(1L))
    unsupported <- names(target)[target > 0 & !available]
    if (length(unsupported) > 0L) {
      stop(sprintf(
        "Arm B PUMS frame lacks support for observed %s levels: %s",
        characteristic,
        paste(unsupported, collapse = ", ")
      ))
    }
  }
  invisible(TRUE)
}

fit_arm_b_ipf <- function(
  frame,
  targets,
  base_weights = frame$base_weight,
  tolerance = ARM_B_IPF_TOLERANCE,
  max_iterations = ARM_B_IPF_MAX_ITERATIONS
) {
  if (length(tolerance) != 1L || !is.finite(tolerance) || tolerance <= 0) {
    stop("Arm B IPF tolerance must be one finite, positive number.")
  }
  if (length(max_iterations) != 1L || is.na(max_iterations) ||
      max_iterations < 1 || max_iterations != as.integer(max_iterations)) {
    stop("Arm B IPF max_iterations must be a positive integer.")
  }
  arm_b_validate_ipf_inputs(frame, targets, base_weights)

  target_total <- sum(base_weights)
  normalized_targets <- lapply(targets, function(target) target / sum(target))
  weights <- as.numeric(base_weights)
  convergence_rows <- vector("list", max_iterations)
  converged <- FALSE

  for (iteration in seq_len(max_iterations)) {
    for (characteristic in names(normalized_targets)) {
      target <- normalized_targets[[characteristic]]
      values <- as.character(frame[[characteristic]])
      current <- vapply(names(target), function(level) sum(weights[values == level]), numeric(1L))
      impossible <- target > 0 & current <= 0
      if (any(impossible)) {
        stop(sprintf(
          "Arm B IPF lost support for %s levels during fitting: %s",
          characteristic,
          paste(names(target)[impossible], collapse = ", ")
        ))
      }
      factors <- ifelse(target == 0, 0, target * target_total / current)
      weights <- weights * unname(factors[match(values, names(target))])
    }

    errors <- vapply(names(normalized_targets), function(characteristic) {
      target <- normalized_targets[[characteristic]]
      values <- as.character(frame[[characteristic]])
      fitted <- vapply(names(target), function(level) sum(weights[values == level]), numeric(1L))
      max(abs(fitted / sum(weights) - target))
    }, numeric(1L))
    max_error <- max(errors)
    convergence_rows[[iteration]] <- data.frame(
      iteration = iteration,
      max_absolute_margin_error = max_error,
      stringsAsFactors = FALSE
    )
    if (max_error <= tolerance) {
      converged <- TRUE
      convergence_rows <- convergence_rows[seq_len(iteration)]
      break
    }
  }

  if (!converged) {
    stop(sprintf(
      "Arm B IPF did not converge within %d iterations; final maximum margin error was %.12g.",
      max_iterations,
      max_error
    ))
  }
  if (any(!is.finite(weights)) || any(weights < 0) || sum(weights > 0) < 1L) {
    stop("Arm B IPF produced invalid fitted weights.")
  }

  list(
    weights = weights,
    convergence = do.call(rbind, convergence_rows),
    iterations = length(convergence_rows),
    max_error = max_error,
    tolerance = tolerance
  )
}

arm_b_integer_targets <- function(targets, n) {
  if (!is.list(targets) || length(targets) == 0L || is.null(names(targets)) ||
      any(names(targets) == "")) {
    stop("Arm B balanced draw targets must be a named, non-empty list of margins.")
  }

  counts <- lapply(names(targets), function(characteristic) {
    target <- targets[[characteristic]]
    if (is.null(names(target)) || any(names(target) == "") || anyDuplicated(names(target)) ||
        any(!is.finite(target)) || any(target < 0) || !is.finite(sum(target)) || sum(target) <= 0) {
      stop(sprintf("Arm B balanced draw target margin %s is invalid.", characteristic))
    }
    expected <- n * target / sum(target)
    rounded <- round(expected)
    if (any(abs(expected - rounded) > 1e-8) || sum(rounded) != n) {
      stop(sprintf(
        "Arm B balanced draw target margin %s does not produce integer counts for a draw of %d.",
        characteristic,
        n
      ))
    }
    stats::setNames(as.integer(rounded), names(target))
  })
  stats::setNames(counts, names(targets))
}

draw_arm_b <- function(
  frame,
  fitted_weights,
  targets,
  n = ARM_B_DRAW_N,
  seed = ARM_B_SEED,
  max_attempts = ARM_B_BALANCED_DRAW_MAX_ATTEMPTS
) {
  if (length(n) != 1L || is.na(n) || n < 1 || n != as.integer(n)) {
    stop("Arm B draw size must be a positive integer.")
  }
  if (length(max_attempts) != 1L || is.na(max_attempts) || max_attempts < 1 ||
      max_attempts != as.integer(max_attempts)) {
    stop("Arm B balanced draw max_attempts must be a positive integer.")
  }
  if (length(fitted_weights) != nrow(frame) || any(!is.finite(fitted_weights)) ||
      any(fitted_weights < 0)) {
    stop("Arm B fitted weights must be finite, non-negative, and have one value per PUMS row.")
  }
  if (sum(fitted_weights > 0) < n) {
    stop(sprintf(
      "Arm B raked PUMS frame has only %d positive-weight records; cannot draw %d without replacement.",
      sum(fitted_weights > 0),
      n
    ))
  }

  target_counts <- arm_b_integer_targets(targets, n)
  characteristics <- names(target_counts)
  arm_b_require_columns(frame, characteristics, "Arm B balanced draw frame")
  for (characteristic in characteristics) {
    values <- as.character(frame[[characteristic]])
    if (anyNA(values) || any(!values %in% names(target_counts[[characteristic]]))) {
      stop(sprintf(
        "Arm B balanced draw frame contains unsupported %s levels.",
        characteristic
      ))
    }
  }

  positive_rows <- which(fitted_weights > 0)
  cell_factors <- lapply(characteristics, function(characteristic) {
    factor(
      as.character(frame[[characteristic]][positive_rows]),
      levels = names(target_counts[[characteristic]])
    )
  })
  cell_id <- do.call(interaction, c(cell_factors, list(drop = TRUE, lex.order = TRUE)))
  rows_by_cell <- split(positive_rows, cell_id)
  first_rows <- vapply(rows_by_cell, function(rows) rows[[1L]], integer(1L))
  cells <- frame[first_rows, characteristics, drop = FALSE]
  capacity <- lengths(rows_by_cell)
  cell_weight <- vapply(
    rows_by_cell,
    function(rows) sum(fitted_weights[rows]),
    numeric(1L)
  )

  set.seed(seed)
  chosen_cell_counts <- NULL
  for (attempt in seq_len(max_attempts)) {
    remaining_targets <- lapply(target_counts, identity)
    remaining_capacity <- capacity
    chosen <- integer(length(capacity))
    greedy_draws <- max(0L, n - 24L)

    for (draw_index in seq_len(greedy_draws)) {
      eligible <- remaining_capacity > 0L
      for (characteristic in characteristics) {
        remaining_for_cell <- remaining_targets[[characteristic]][
          as.character(cells[[characteristic]])
        ]
        eligible <- eligible & remaining_for_cell > 0L
      }
      candidates <- which(eligible)
      if (length(candidates) == 0L) {
        break
      }

      probabilities <- cell_weight[candidates] *
        remaining_capacity[candidates] / capacity[candidates]
      picked_cell <- candidates[[sample.int(
        length(candidates),
        size = 1L,
        prob = probabilities
      )]]
      chosen[[picked_cell]] <- chosen[[picked_cell]] + 1L
      remaining_capacity[[picked_cell]] <- remaining_capacity[[picked_cell]] - 1L
      for (characteristic in characteristics) {
        level <- as.character(cells[[characteristic]][[picked_cell]])
        remaining_targets[[characteristic]][[level]] <-
          remaining_targets[[characteristic]][[level]] - 1L
      }
    }

    if (sum(chosen) == greedy_draws) {
      search_nodes <- 0L
      complete_tail <- function(tail_capacity, tail_targets, tail_chosen) {
        search_nodes <<- search_nodes + 1L
        if (search_nodes > 100000L) {
          return(NULL)
        }
        remaining_n <- sum(tail_targets[[1L]])
        if (remaining_n == 0L) {
          return(tail_chosen)
        }

        eligible <- tail_capacity > 0L
        for (characteristic in characteristics) {
          remaining_for_cell <- tail_targets[[characteristic]][
            as.character(cells[[characteristic]])
          ]
          eligible <- eligible & remaining_for_cell > 0L
        }
        if (!any(eligible)) {
          return(NULL)
        }

        constraints <- list()
        constraint_index <- 0L
        for (characteristic in characteristics) {
          for (level in names(tail_targets[[characteristic]])) {
            needed <- tail_targets[[characteristic]][[level]]
            if (needed <= 0L) {
              next
            }
            supports <- eligible & as.character(cells[[characteristic]]) == level
            available <- sum(tail_capacity[supports])
            if (available < needed) {
              return(NULL)
            }
            constraint_index <- constraint_index + 1L
            constraints[[constraint_index]] <- list(
              characteristic = characteristic,
              level = level,
              slack = available - needed
            )
          }
        }
        slacks <- vapply(constraints, function(constraint) constraint$slack, numeric(1L))
        tightest <- constraints[[which.min(slacks)]]
        candidates <- which(
          eligible & as.character(cells[[tightest$characteristic]]) == tightest$level
        )
        candidate_probabilities <- cell_weight[candidates] *
          tail_capacity[candidates] / capacity[candidates]
        candidate_order <- candidates[sample.int(
          length(candidates),
          size = length(candidates),
          replace = FALSE,
          prob = candidate_probabilities
        )]

        for (picked_cell in candidate_order) {
          next_capacity <- tail_capacity
          next_capacity[[picked_cell]] <- next_capacity[[picked_cell]] - 1L
          next_targets <- lapply(tail_targets, identity)
          for (characteristic in characteristics) {
            level <- as.character(cells[[characteristic]][[picked_cell]])
            next_targets[[characteristic]][[level]] <-
              next_targets[[characteristic]][[level]] - 1L
          }
          next_chosen <- tail_chosen
          next_chosen[[picked_cell]] <- next_chosen[[picked_cell]] + 1L
          solution <- complete_tail(next_capacity, next_targets, next_chosen)
          if (!is.null(solution)) {
            return(solution)
          }
        }
        NULL
      }

      completed <- complete_tail(remaining_capacity, remaining_targets, chosen)
      if (!is.null(completed)) {
        chosen_cell_counts <- completed
        break
      }
    }
  }

  if (is.null(chosen_cell_counts)) {
    stop(sprintf(
      paste0(
        "Arm B could not construct a without-replacement draw matching every observed margin ",
        "after %d fixed-seed attempts; the joint PUMS support may be insufficient."
      ),
      max_attempts
    ))
  }

  picks <- unlist(lapply(which(chosen_cell_counts > 0L), function(cell_index) {
    rows <- rows_by_cell[[cell_index]]
    rows[sample.int(
      length(rows),
      size = chosen_cell_counts[[cell_index]],
      replace = FALSE,
      prob = fitted_weights[rows]
    )]
  }), use.names = FALSE)
  picks <- picks[sample.int(length(picks))]
  selected <- frame[picks, , drop = FALSE]

  for (characteristic in characteristics) {
    actual <- as.integer(table(factor(
      selected[[characteristic]],
      levels = names(target_counts[[characteristic]])
    )))
    if (!identical(actual, unname(target_counts[[characteristic]]))) {
      stop(sprintf("Arm B balanced draw failed its %s margin invariant.", characteristic))
    }
  }
  selected
}

harmonize_arm_b_synthetic <- function(selected) {
  arm_b_require_columns(
    selected,
    c("donor_id", "age", "age_band", "gender", "household_income", "income_band", "state"),
    "Arm B synthetic draw"
  )
  if (nrow(selected) == 0L || anyDuplicated(selected$donor_id)) {
    stop("Arm B synthetic draw must contain unique PUMS donors.")
  }
  data.frame(
    synthetic_id = sprintf("arm_b_%03d", seq_len(nrow(selected))),
    age = selected$age,
    age_band = selected$age_band,
    gender = selected$gender,
    household_income = selected$household_income,
    income_band = selected$income_band,
    state = selected$state,
    stringsAsFactors = FALSE
  )
}

audit_arm_b_margins <- function(frame, fitted_weights, selected, targets, real_n) {
  rows <- lapply(names(targets), function(characteristic) {
    target <- targets[[characteristic]] / sum(targets[[characteristic]])
    levels <- names(target)
    values <- as.character(frame[[characteristic]])
    selected_values <- as.character(selected[[characteristic]])
    raked_weight <- vapply(levels, function(level) sum(fitted_weights[values == level]), numeric(1L))
    selected_n <- as.integer(table(factor(selected_values, levels = levels)))
    data.frame(
      characteristic = characteristic,
      level = levels,
      target_n = as.integer(round(target * real_n)),
      target_proportion = unname(target),
      raked_weight = raked_weight,
      raked_proportion = raked_weight / sum(fitted_weights),
      selected_n = selected_n,
      selected_proportion = selected_n / nrow(selected),
      raked_difference_percentage_points = 100 * (raked_weight / sum(fitted_weights) - target),
      selected_difference_percentage_points = 100 * (selected_n / nrow(selected) - target),
      stringsAsFactors = FALSE
    )
  })
  audit <- do.call(rbind, rows)
  rownames(audit) <- NULL
  audit
}

run_arm_b <- function(
  housing,
  person,
  real_data,
  draw_n = ARM_B_DRAW_N,
  seed = ARM_B_SEED,
  expected_real_rows = ARM_B_DRAW_N,
  tolerance = ARM_B_IPF_TOLERANCE,
  max_iterations = ARM_B_IPF_MAX_ITERATIONS,
  real_id_column = "Response ID"
) {
  real <- harmonize_arm_b_real(
    real_data,
    expected_rows = expected_real_rows,
    id_column = real_id_column
  )
  pums <- build_arm_b_pums_frame(housing, person)
  targets <- arm_b_targets(real)
  fitted <- fit_arm_b_ipf(
    pums$frame,
    targets,
    tolerance = tolerance,
    max_iterations = max_iterations
  )
  selected <- draw_arm_b(
    pums$frame,
    fitted$weights,
    targets,
    n = draw_n,
    seed = seed
  )
  synthetic <- harmonize_arm_b_synthetic(selected)
  margin_audit <- audit_arm_b_margins(
    pums$frame,
    fitted$weights,
    selected,
    targets,
    real_n = nrow(real)
  )

  stopifnot(
    nrow(real) == expected_real_rows,
    nrow(synthetic) == draw_n,
    !anyDuplicated(synthetic$synthetic_id),
    fitted$max_error <= tolerance,
    max(abs(margin_audit$raked_difference_percentage_points)) <= 100 * tolerance,
    all(margin_audit$selected_n == margin_audit$target_n)
  )

  list(
    seed = as.integer(seed),
    draw_n = as.integer(draw_n),
    match_characteristics = names(targets),
    source_frame_n = nrow(pums$frame),
    frame_audit = pums$audit,
    convergence = fitted$convergence,
    margin_audit = margin_audit,
    synthetic = synthetic
  )
}
