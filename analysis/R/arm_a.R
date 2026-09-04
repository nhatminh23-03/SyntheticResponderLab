ARM_A_DRAW_N <- 600L
ARM_A_SEED <- 20260904L
ARM_A_OUTDOOR_PREFIX <- "PQ1:"

ARM_A_REAL_INCOME_LEVELS <- c(
  "$0 - $24,999",
  "$25,000 - $49,999",
  "$50,000 - $74,999",
  "$75,000 - $99,999",
  "$100,000 - $199,999",
  "$200,000 or more"
)
ARM_A_OUTDOOR_PASS_LEVELS <- c("Yes", "I'm not sure, but possibly.")
ARM_A_OUTDOOR_LEVELS <- c(ARM_A_OUTDOOR_PASS_LEVELS, "No")

arm_a_require_columns <- function(frame, columns, label) {
  missing <- setdiff(columns, names(frame))
  if (length(missing) > 0L) {
    stop(sprintf("%s is missing required columns: %s", label, paste(missing, collapse = ", ")))
  }
}

arm_a_number <- function(values) {
  suppressWarnings(as.numeric(as.character(values)))
}

validate_arm_a_pums_sources <- function(housing, person) {
  sources <- list(housing = housing, person = person)
  for (source_name in names(sources)) {
    frame <- sources[[source_name]]
    label <- sprintf("Arm A %s PUMS frame", source_name)
    arm_a_require_columns(frame, "ST", label)
    state <- arm_a_number(frame$ST)
    if (any(!is.finite(state)) || any(state != 6)) {
      stop(sprintf("%s must contain only California records (ST = 06).", label))
    }
  }
}

arm_a_prefixed_column <- function(frame, prefix) {
  matches <- names(frame)[startsWith(names(frame), prefix)]
  if (length(matches) != 1L) {
    stop(sprintf(
      "Real panel must contain exactly one column beginning %s; found %d.",
      shQuote(prefix),
      length(matches)
    ))
  }
  matches[[1L]]
}

arm_a_age_band <- function(age) {
  ifelse(
    age < MIN_AGE | age > MAX_AGE,
    "Outside 30-65",
    ifelse(age <= 39, "30-39", ifelse(age <= 49, "40-49", ifelse(age <= 59, "50-59", "60-65")))
  )
}

arm_a_income_band <- function(income) {
  ifelse(
    income < MIN_HOUSEHOLD_INCOME,
    "Below $100,000",
    ifelse(income < 200000, "$100,000 - $199,999", "$200,000 or more")
  )
}

harmonize_arm_a_synthetic <- function(selected) {
  arm_a_require_columns(
    selected,
    c("AGEP", "SEX", "ST", "BLD", "WGTP", "household_income"),
    "Arm A synthetic draw"
  )
  if (nrow(selected) == 0L) {
    stop("Arm A synthetic draw contains no respondents.")
  }

  age <- arm_a_number(selected$AGEP)
  income <- arm_a_number(selected$household_income)
  sex <- arm_a_number(selected$SEX)
  state <- arm_a_number(selected$ST)
  structure_type <- arm_a_number(selected$BLD)
  weight <- arm_a_number(selected$WGTP)

  if (any(!is.finite(age)) || any(age < MIN_AGE | age > MAX_AGE)) {
    stop("Arm A synthetic draw violates the inclusive age 30-65 screen.")
  }
  if (any(!is.finite(income)) || any(income < MIN_HOUSEHOLD_INCOME)) {
    stop("Arm A synthetic draw violates the adjusted $100,000 income screen.")
  }
  if (any(!is.finite(structure_type)) || any(structure_type != DETACHED_SINGLE_FAMILY)) {
    stop("Arm A synthetic draw violates the detached single-family screen.")
  }
  if (any(!is.finite(weight)) || any(weight <= 0)) {
    stop("Arm A synthetic draw must retain finite, positive WGTP values.")
  }
  if (any(!is.finite(sex)) || any(!sex %in% c(1, 2))) {
    stop("Arm A synthetic SEX values must use the ACS codes 1 or 2.")
  }
  if (any(!is.finite(state)) || any(state != 6)) {
    stop("Arm A synthetic input must contain only California PUMS records (ST = 06).")
  }

  data.frame(
    synthetic_id = sprintf("arm_a_%03d", seq_len(nrow(selected))),
    age = age,
    gender = ifelse(sex == 1, "Male", "Female"),
    household_income = income,
    age_band = arm_a_age_band(age),
    income_band = arm_a_income_band(income),
    state_group = "California",
    outdoor_space_screen = "Pass",
    hard_screen_proxy = "Pass all three",
    stringsAsFactors = FALSE
  )
}

harmonize_arm_a_real <- function(
  real_data,
  expected_rows = ARM_A_DRAW_N,
  id_column = "Response ID"
) {
  if (length(id_column) != 1L || is.na(id_column) || !nzchar(id_column)) {
    stop("Arm A real respondent ID must name exactly one non-empty column.")
  }
  arm_a_require_columns(
    real_data,
    c(id_column, "Status", "Gender", "Age", "Household Income", "State"),
    "real panel"
  )
  outdoor_column <- arm_a_prefixed_column(real_data, ARM_A_OUTDOOR_PREFIX)
  status <- trimws(as.character(real_data$Status))
  completed <- real_data[!is.na(status) & status == "Completed", , drop = FALSE]
  if (nrow(completed) != expected_rows) {
    stop(sprintf("Expected exactly %d completed real respondents; found %d.", expected_rows, nrow(completed)))
  }

  response_ids <- trimws(as.character(completed[[id_column]]))
  if (any(is.na(completed[[id_column]])) || any(response_ids == "") || anyDuplicated(response_ids)) {
    stop("Completed real respondent IDs must be present and unique.")
  }

  age <- arm_a_number(completed$Age)
  if (any(!is.finite(age))) {
    stop("Completed real respondent ages must be complete and numeric.")
  }

  income <- trimws(as.character(completed[["Household Income"]]))
  unknown_income <- setdiff(unique(income), ARM_A_REAL_INCOME_LEVELS)
  if (length(unknown_income) > 0L) {
    stop(sprintf(
      "Completed real respondent income contains unsupported levels: %s",
      paste(unknown_income, collapse = ", ")
    ))
  }

  gender <- trimws(as.character(completed$Gender))
  state <- trimws(as.character(completed$State))
  outdoor <- trimws(as.character(completed[[outdoor_column]]))
  if (any(is.na(completed$Gender)) || any(gender == "")) {
    stop("Completed real respondent gender must be present.")
  }
  if (any(is.na(completed$State)) || any(state == "")) {
    stop("Completed real respondent state must be present.")
  }
  if (any(is.na(completed[[outdoor_column]])) || any(outdoor == "")) {
    stop("Completed real respondent outdoor-space screener must be present.")
  }
  unknown_outdoor <- setdiff(unique(outdoor), ARM_A_OUTDOOR_LEVELS)
  if (length(unknown_outdoor) > 0L) {
    stop(sprintf(
      "Completed real respondent outdoor-space screener contains unsupported levels: %s",
      paste(unknown_outdoor, collapse = ", ")
    ))
  }

  income_band <- ifelse(
    income == "$100,000 - $199,999",
    "$100,000 - $199,999",
    ifelse(income == "$200,000 or more", "$200,000 or more", "Below $100,000")
  )
  passes_age <- age >= MIN_AGE & age <= MAX_AGE
  passes_income <- income_band != "Below $100,000"
  passes_outdoor <- outdoor %in% ARM_A_OUTDOOR_PASS_LEVELS

  data.frame(
    age = age,
    gender = ifelse(gender %in% c("Female", "Male"), gender, "Other"),
    age_band = arm_a_age_band(age),
    income_band = income_band,
    state_group = ifelse(tolower(state) == "california", "California", "Other state"),
    outdoor_space_screen = ifelse(passes_outdoor, "Pass", "Does not pass"),
    hard_screen_proxy = ifelse(
      passes_age & passes_income & passes_outdoor,
      "Pass all three",
      "Does not pass all three"
    ),
    stringsAsFactors = FALSE
  )
}

arm_a_comparison_specifications <- function() {
  list(
    age_band = c("30-39", "40-49", "50-59", "60-65", "Outside 30-65"),
    income_band = c("Below $100,000", "$100,000 - $199,999", "$200,000 or more"),
    gender = c("Female", "Male", "Other"),
    state_group = c("California", "Other state"),
    outdoor_space_screen = c("Pass", "Does not pass"),
    hard_screen_proxy = c("Pass all three", "Does not pass all three")
  )
}

arm_a_counts <- function(values, levels) {
  if (any(!values %in% levels)) {
    stop("Arm A comparison encountered a value outside its registered levels.")
  }
  as.integer(table(factor(values, levels = levels)))
}

compare_arm_a <- function(synthetic, real) {
  specifications <- arm_a_comparison_specifications()
  rows <- lapply(names(specifications), function(characteristic) {
    levels <- specifications[[characteristic]]
    synthetic_counts <- arm_a_counts(synthetic[[characteristic]], levels)
    real_counts <- arm_a_counts(real[[characteristic]], levels)
    data.frame(
      characteristic = characteristic,
      level = levels,
      synthetic_n = synthetic_counts,
      synthetic_proportion = synthetic_counts / nrow(synthetic),
      real_n = real_counts,
      real_proportion = real_counts / nrow(real),
      difference_percentage_points = 100 * (
        synthetic_counts / nrow(synthetic) - real_counts / nrow(real)
      ),
      stringsAsFactors = FALSE
    )
  })
  comparison <- do.call(rbind, rows)
  rownames(comparison) <- NULL

  totals <- split(comparison, comparison$characteristic)
  stopifnot(
    all(vapply(totals, function(frame) sum(frame$synthetic_n), integer(1L)) == nrow(synthetic)),
    all(vapply(totals, function(frame) sum(frame$real_n), integer(1L)) == nrow(real))
  )
  comparison
}

summarize_arm_a_age <- function(synthetic, real) {
  data.frame(
    statistic = c("mean", "standard_deviation", "median"),
    synthetic = c(mean(synthetic$age), stats::sd(synthetic$age), stats::median(synthetic$age)),
    real = c(mean(real$age), stats::sd(real$age), stats::median(real$age)),
    difference = c(
      mean(synthetic$age) - mean(real$age),
      stats::sd(synthetic$age) - stats::sd(real$age),
      stats::median(synthetic$age) - stats::median(real$age)
    ),
    stringsAsFactors = FALSE
  )
}

arm_a_screen_audit <- function(synthetic, real) {
  synthetic_pass <- sum(synthetic$hard_screen_proxy == "Pass all three")
  real_pass <- sum(real$hard_screen_proxy == "Pass all three")
  data.frame(
    source = c("synthetic Arm A", "real panel"),
    respondents = c(nrow(synthetic), nrow(real)),
    pass_all_three = c(synthetic_pass, real_pass),
    pass_proportion = c(synthetic_pass / nrow(synthetic), real_pass / nrow(real)),
    home_screen_measure = c(
      "ACS BLD=02 detached-single-family proxy",
      "AYTM PQ1 self-reported feasible-or-possible outdoor space"
    ),
    stringsAsFactors = FALSE
  )
}

run_arm_a <- function(
  housing,
  person,
  real_data,
  draw_n = ARM_A_DRAW_N,
  seed = ARM_A_SEED,
  expected_real_rows = ARM_A_DRAW_N,
  real_id_column = "Response ID"
) {
  validate_arm_a_pums_sources(housing, person)
  screened <- screen_pums_frames(housing, person, draw_n = draw_n, seed = seed)
  synthetic <- harmonize_arm_a_synthetic(screened$selected)
  real <- harmonize_arm_a_real(
    real_data,
    expected_rows = expected_real_rows,
    id_column = real_id_column
  )
  comparison <- compare_arm_a(synthetic, real)
  age_summary <- summarize_arm_a_age(synthetic, real)
  screen_audit <- arm_a_screen_audit(synthetic, real)

  stopifnot(
    nrow(synthetic) == draw_n,
    nrow(real) == expected_real_rows,
    all(synthetic$hard_screen_proxy == "Pass all three"),
    all(is.finite(age_summary$synthetic)),
    all(is.finite(age_summary$real)),
    screen_audit$pass_all_three[[1L]] == draw_n
  )

  list(
    seed = as.integer(seed),
    draw_n = as.integer(draw_n),
    funnel = screened$funnel,
    synthetic = synthetic,
    comparison = comparison,
    age_summary = age_summary,
    screen_audit = screen_audit
  )
}
