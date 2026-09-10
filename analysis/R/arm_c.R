ARM_C_DRAW_N <- 256L
ARM_C_SEED <- 20260904L
ARM_C_DATA_DIRECTORY <- path.expand("~/dev/aytm-real-data/neo_smart_living/student_sample")

# Headers and responses remain in the local analysis process. Never print source rows.
arm_c_key <- function(value) {
  value <- sub("^aytm:", "", value)
  value <- sub("[ |:].*$", "", value)
  value <- gsub("[^a-z0-9]", "", gsub("barrier", "", tolower(value), fixed = TRUE))
  value <- sub("^q30vd", "q30", value)
  value <- sub("^q30installspeed$", "q30speed", value)
  value[value == "q10"] <- "q9other"
  value
}

arm_c_match_columns <- function(keys, columns) {
  candidates <- arm_c_key(columns)
  answer <- rep(NA_integer_, length(keys))
  # Longest prefix avoids Q1 consuming Q11 or a concept's more specific identifier.
  for (index in order(nchar(keys), decreasing = TRUE)) {
    available <- which(!seq_along(columns) %in% answer[!is.na(answer)])
    exact <- available[candidates[available] == keys[[index]]]
    prefix <- available[startsWith(candidates[available], keys[[index]]) &
      !grepl("^[0-9]", substring(candidates[available], nchar(keys[[index]]) + 1L))]
    hits <- if (length(exact) > 0L) exact else prefix
    if (length(hits) == 1L) answer[[index]] <- hits
  }
  # A single remaining item in the same numbered question resolves label abbreviations.
  group <- function(x) sub("^((pq|q)[0-9]+).*$", "\\1", x)
  for (index in which(is.na(answer))) {
    unmatched <- which(is.na(answer) & group(keys) == group(keys[[index]]))
    available <- which(!seq_along(columns) %in% answer[!is.na(answer)] &
      group(candidates) == group(keys[[index]]))
    if (length(unmatched) == 1L && length(available) == 1L) answer[[index]] <- available
  }
  if (anyNA(answer) || anyDuplicated(answer)) {
    stop("Arm C header alignment is incomplete or ambiguous; no questions were silently dropped.")
  }
  answer
}

arm_c_align <- function(student, aytm, mapping, expected_questions = 42L) {
  arm_a_require_columns(mapping, c("match_status", "aytm_column", "notes"), "Arm C mapping")
  matched <- mapping[tolower(trimws(mapping$match_status)) == "matched", , drop = FALSE]
  stopifnot(nrow(matched) == expected_questions)
  student_columns <- names(student)[startsWith(names(student), "aytm:")]
  # Resolve mapping topics against the embedded AYTM keys, never student_column text.
  mapping_index <- arm_c_match_columns(arm_c_key(matched$aytm_column), matched$aytm_column)
  stopifnot(identical(mapping_index, seq_len(nrow(matched))))
  # Match the short student aliases to the longer AYTM names, retaining only mapped topics.
  keys <- arm_c_key(student_columns)
  mapped_keys <- arm_c_key(matched$aytm_column)
  reverse <- rep(NA_integer_, length(mapped_keys))
  for (index in seq_along(mapped_keys)) {
    hits <- which(startsWith(mapped_keys[[index]], keys) &
      !grepl("^[0-9]", substring(mapped_keys[[index]], nchar(keys) + 1L)))
    if (length(hits)) reverse[[index]] <- hits[[which.max(nchar(keys[hits]))]]
  }
  # Exact and unique numbered-group matching also handles the remaining abbreviated barrier.
  for (index in which(is.na(reverse) | duplicated(reverse) | duplicated(reverse, fromLast = TRUE))) {
    reverse[[index]] <- NA_integer_
  }
  group_key <- function(x) sub("^((pq|q)[0-9]+).*$", "\\1", x)
  for (index in which(is.na(reverse))) {
    hits <- which(!seq_along(keys) %in% reverse &
      group_key(keys) == group_key(mapped_keys[[index]]))
    if (length(hits) > 1L) {
      suffix <- sub("^(pq|q)[0-9]+", "", mapped_keys[[index]])
      short <- sub("^(pq|q)[0-9]+", "", keys[hits])
      overlap <- nzchar(short) & (vapply(short, function(x) grepl(x, suffix, fixed = TRUE), logical(1L)) |
        grepl(suffix, short, fixed = TRUE))
      hits <- hits[overlap]
    }
    if (length(hits) == 1L) reverse[[index]] <- hits
  }
  if (anyNA(reverse) || anyDuplicated(reverse)) stop("Arm C student prefix alignment is incomplete or ambiguous.")
  aytm_index <- arm_c_match_columns(mapped_keys, names(aytm))
  data.frame(
    question_id = sub("^aytm:([A-Za-z0-9_]+).*$", "\\1", student_columns[reverse]),
    student_column = student_columns[reverse],
    aytm_column = names(aytm)[aytm_index],
    notes = matched$notes,
    stringsAsFactors = FALSE
  )
}

arm_c_number <- function(values) {
  suppressWarnings(as.numeric(sub("^([1-5])\\s*[-–:].*$", "\\1", trimws(as.character(values)))))
}

arm_c_income <- function(values) {
  cleaned <- gsub(",", "", as.character(values), fixed = TRUE)
  lower <- suppressWarnings(as.numeric(sub("^[^0-9]*([0-9]+).*$", "\\1", cleaned)))
  lower[grepl("under|less|below", cleaned, ignore.case = TRUE)] <- 0
  missing <- is.na(values) | !nzchar(trimws(as.character(values))) |
    grepl("prefer|declin|not.*(say|answer|disclos)", cleaned, ignore.case = TRUE)
  if (any(!is.finite(lower) & !missing)) stop("Arm C income bands could not be harmonized.")
  lower[missing] <- NA_real_
  as.character(cut(lower, c(-Inf, 49999, 74999, 99999, 199999, Inf),
    labels = c("Under $50,000", "$50,000-$74,999", "$75,000-$99,999", "$100,000-$199,999", "$200,000+")))
}

arm_c_age <- function(values) {
  lower <- suppressWarnings(as.numeric(sub("^[^0-9]*([0-9]+).*$", "\\1", as.character(values))))
  result <- arm_b_age_band(lower)
  if (anyNA(result)) stop("Arm C age bands could not be harmonized to adult six-band ages.")
  result
}

arm_c_category <- function(values) {
  tolower(trimws(gsub("[^[:alnum:] ]", "", as.character(values))))
}

arm_c_harmonize <- function(student, aytm, alignment) {
  student_output <- data.frame(respondent_id = sprintf("student_%03d", seq_len(nrow(student))))
  aytm_output <- data.frame(respondent_id = sprintf("aytm_%03d", seq_len(nrow(aytm))))
  audit <- data.frame(question_id = alignment$question_id, question_type = "categorical",
    treatment = "Compare category distributions", stringsAsFactors = FALSE)
  for (index in seq_len(nrow(alignment))) {
    id <- alignment$question_id[[index]]
    key <- tolower(id)
    notes <- tolower(alignment$notes[[index]])
    if (is.na(notes)) notes <- ""
    left <- trimws(as.character(student[[alignment$student_column[[index]]]]))
    right <- trimws(as.character(aytm[[alignment$aytm_column[[index]]]]))
    demographic <- grepl("age|income|gender|race|employment", key)
    numeric_left <- arm_c_number(left)
    numeric_right <- arm_c_number(right)
    scale <- all(is.na(left) | left == "" | numeric_left %in% 1:5) &&
      all(is.na(right) | right == "" | numeric_right %in% 1:5)
    excluded <- grepl("multi|open.end|qualitative", notes) ||
      (!demographic && any(grepl(",", left), na.rm = TRUE))
    if (excluded) {
      audit$question_type[[index]] <- "excluded"
      audit$treatment[[index]] <- "Excluded: multi-select or open-ended; qualitative only, no model calls"
      next
    }
    if (grepl("income", key)) {
      left <- arm_c_income(left); right <- arm_c_income(right)
      audit$treatment[[index]] <- "Income: merge both AYTM under-$50k buckets and both student $100k-$199,999 buckets; retain $50k-$74,999, $75k-$99,999 and $200k+"
    } else if (key == "age") {
      left <- arm_c_age(left); right <- arm_c_age(right)
      audit$treatment[[index]] <- "Age: raw AYTM ages and student bands collapsed to 18-24, 25-34, 35-44, 45-54, 55-64, 65+"
    } else if (grepl("1.?5|compare means|compare mean", notes) || (notes == "" && scale)) {
      if (!scale) stop("Arm C scale item contains unsupported values.")
      left <- numeric_left; right <- numeric_right
      audit$question_type[[index]] <- "continuous"
      audit$treatment[[index]] <- "Same 1-5 scale; strip AYTM anchor text; compare means (blank notes use verified 1-5 coding)"
    } else {
      left <- arm_c_category(left); right <- arm_c_category(right)
      if (grepl("gender", key)) {
        left[!left %in% c("female", "male")] <- "other"
        right[!right %in% c("female", "male")] <- "other"
      } else if (grepl("employment", key)) {
        collapse <- function(x) ifelse(is.na(x) | !nzchar(x), NA_character_,
          ifelse(grepl("unemploy|not employ|not working|retir|student|homemaker|disab", x),
            "not employed / other", ifelse(grepl("employ|full.?time|part.?time|working|business", x),
              "employed", "not employed / other")))
        left <- collapse(left); right <- collapse(right)
      } else if (grepl("race", key)) {
        collapse <- function(x) ifelse(is.na(x) | !nzchar(x), NA_character_,
          ifelse(grepl("white|caucasian", x) & !grepl("black|asian|hispanic|latino|multi", x),
            "white", "other / multiracial"))
        left <- collapse(left); right <- collapse(right)
      } else if (startsWith(key, "pq1")) {
        left <- ifelse(left == "no", "no", ifelse(left == "yes", "yes", "possibly"))
        right <- ifelse(right == "no", "no", ifelse(right == "yes", "yes", "possibly"))
      } else {
        shared <- intersect(unique(left[!is.na(left) & nzchar(left)]), unique(right[!is.na(right) & nzchar(right)]))
        if (length(shared) == 0L) {
          stop(sprintf("Arm C %s has no shared categories; explicit harmonization is required.", id))
        }
        left[!is.na(left) & nzchar(left) & !left %in% shared] <- "other / not shared"
        right[!is.na(right) & nzchar(right) & !right %in% shared] <- "other / not shared"
      }
      audit$treatment[[index]] <- "Normalize case/punctuation; retain shared categories, collapse survey-specific categories to Other / not shared; gender to female/male/other; race to White vs other/multiracial; employment to employed vs not employed/other; PQ1 to yes/no/possibly"
    }
    student_output[[id]] <- left
    aytm_output[[id]] <- right
  }
  list(student = student_output, aytm = aytm_output, audit = audit)
}

arm_c_compare <- function(real, synthetic, registry, seed = ARM_C_SEED) {
  registered <- validate_question_registry(registry)
  results <- equivalence <- list()
  audit <- data.frame(question_id = registered$question_id, real_missing = 0L,
    synthetic_missing = 0L, status = "Tested", stringsAsFactors = FALSE)
  arm_a_require_columns(real, registered$question_id, "Arm C student responses")
  arm_a_require_columns(synthetic, c("synthetic_id", registered$question_id), "Arm C synthetic responses")
  for (index in seq_len(nrow(registered))) {
    id <- registered$question_id[[index]]
    present <- function(x) !is.na(x) & nzchar(trimws(as.character(x)))
    a <- real[present(real[[id]]), c("respondent_id", id), drop = FALSE]
    b <- synthetic[present(synthetic[[id]]), c("synthetic_id", id), drop = FALSE]
    audit$real_missing[[index]] <- nrow(real) - nrow(a)
    audit$synthetic_missing[[index]] <- nrow(synthetic) - nrow(b)
    if (nrow(a) < 2L || nrow(b) < 2L || length(unique(c(a[[id]], b[[id]]))) < 2L) {
      audit$status[[index]] <- "Not estimable: fewer than two complete observations or constant pooled response"
      next
    }
    tested <- run_test_battery(a, b, registered[index, , drop = FALSE],
      "respondent_id", "synthetic_id", seed = seed + index - 1L)
    results[[length(results) + 1L]] <- tested$results
    equivalence[[length(equivalence) + 1L]] <- tested$equivalence
  }
  list(results = do.call(rbind, results), equivalence = do.call(rbind, equivalence), audit = audit)
}

run_arm_c <- function(housing, person, student_data, aytm_data, mapping,
  synthetic_data, registry, seed = ARM_C_SEED,
  expected_student_rows = ARM_C_DRAW_N, expected_aytm_rows = ARM_B_DRAW_N,
  expected_questions = 42L) {
  stopifnot(nrow(student_data) == expected_student_rows, nrow(aytm_data) == expected_aytm_rows)
  alignment <- arm_c_align(student_data, aytm_data, mapping, expected_questions)
  harmonized <- arm_c_harmonize(student_data, aytm_data, alignment)
  demographic_id <- function(pattern) {
    hits <- alignment$question_id[grepl(pattern, alignment$question_id, ignore.case = TRUE)]
    if (length(hits) != 1L) stop("Arm C requires one age, gender and income question.")
    hits[[1L]]
  }
  ids <- c(age_band = demographic_id("^Age$"), gender = demographic_id("gender"),
    income_band = demographic_id("income"))
  real <- harmonized$student
  pums <- build_arm_b_pums_frame(housing, person)
  frame <- pums$frame
  frame$income_band <- arm_c_income(frame$household_income)
  frame$gender <- tolower(frame$gender)
  targets <- lapply(names(ids), function(name) {
    values <- real[[ids[[name]]]]
    levels <- sort(unique(frame[[name]]))
    observed <- values[!is.na(values) & values %in% levels]
    if (!length(observed)) stop("Arm C has no supported observations for a demographic margin.")
    counts <- as.numeric(table(factor(observed, levels = levels)))
    expected <- counts / sum(counts) * nrow(real)
    quotas <- floor(expected)
    remainder <- nrow(real) - sum(quotas)
    if (remainder > 0L) {
      extra <- order(expected - quotas, decreasing = TRUE)[seq_len(remainder)]
      quotas[extra] <- quotas[extra] + 1L
    }
    stopifnot(sum(quotas) == nrow(real))
    stats::setNames(quotas / nrow(real), levels)
  })
  names(targets) <- names(ids)
  calibration_audit <- data.frame(characteristic = names(ids),
    observed_supported_n = vapply(names(ids), function(name) {
      sum(!is.na(real[[ids[[name]]]]) & real[[ids[[name]]]] %in% frame[[name]])
    }, integer(1L)), respondents = nrow(real), stringsAsFactors = FALSE)
  fitted <- fit_arm_b_ipf(frame, targets)
  selected <- draw_arm_b(frame, fitted$weights, targets, n = nrow(real), seed = seed)
  selected$synthetic_id <- sprintf("arm_c_%03d", seq_len(nrow(selected)))
  stopifnot(nrow(selected) == nrow(real), !anyDuplicated(selected$donor_id))
  # Responses must have been produced independently for precisely this fixed-seed draw.
  arm_a_require_columns(synthetic_data, "synthetic_id", "Arm C synthetic responses")
  if (anyDuplicated(synthetic_data$synthetic_id) ||
      !setequal(synthetic_data$synthetic_id, selected$synthetic_id)) {
    stop("Arm C synthetic response IDs must match the fixed-seed Arm C draw exactly.")
  }
  synthetic_data <- synthetic_data[match(selected$synthetic_id, synthetic_data$synthetic_id), , drop = FALSE]
  for (name in names(ids)) synthetic_data[[ids[[name]]]] <- selected[[name]]
  registered <- validate_question_registry(registry)
  quantitative <- harmonized$audit[harmonized$audit$question_type != "excluded", , drop = FALSE]
  if (!setequal(registered$question_id, quantitative$question_id)) stop("Arm C registry must cover every quantitative matched question exactly.")
  registered <- registered[match(quantitative$question_id, registered$question_id), , drop = FALSE]
  if (!identical(registered$question_type, quantitative$question_type)) stop("Arm C registry types must follow mapping notes and harmonization audit.")
  tested <- arm_c_compare(real, synthetic_data, registered, seed)
  margin_audit <- audit_arm_b_margins(frame, fitted$weights, selected, targets, nrow(real))
  stopifnot(all(margin_audit$selected_n == margin_audit$target_n))
  list(seed = as.integer(seed), draw_n = nrow(selected), synthetic = selected,
    frame_audit = pums$audit, convergence = fitted$convergence, margin_audit = margin_audit,
    calibration_audit = calibration_audit, question_audit = harmonized$audit, battery = tested,
    limitations = c(
      "Unscreened comparison: all 256 student respondents are retained. Student PQ1 includes No; AYTM screened No out before fielding and its 600 contains none. The samples are screened differently.",
      "AYTM is a national panel; the student survey is Southern-California-based. Geography cannot be controlled for because the student survey never asked for it.",
      "Arm C validates none of Van Westendorp pricing, education, career, relationship status, parental status or state/region: these are AYTM-only.",
      "Demographic nonresponse and gender categories unsupported by PUMS are omitted only from calibration targets, never from the 256-person sample. Supported marginal proportions are expanded to 256 with largest-remainder integer rounding; supported counts are reported. Age, gender and income margins are matched by IPF and a balanced draw without replacement; matching these margins is by construction, not independent validation. Race and employment are compared but not balanced; PUMS householders do not represent all convenience-sample individuals.",
      "AYTM answers are used only locally for common coding, never as the Arm C reference sample or to generate synthetic answers. All tests compare students against independently supplied Arm C synthetic responses.",
      "Multi-select and open-ended questions are excluded from quantitative tests, including comma-joined outreach answers despite single-select mapping notes. Missing answers are removed per item with counts reported. Equivalence margins must be supplied before analysis; synthetic categorical answers must use the audited common coding."
    ))
}
