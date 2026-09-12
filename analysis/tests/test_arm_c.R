source(file.path(repo_root, "analysis", "run_all.R"), local = TRUE)
source(file.path(repo_root, "analysis", "tests", "fixture_arm_c.R"), local = TRUE)

assert_error <- function(expression, pattern) {
  message <- tryCatch({ force(expression); NULL }, error = function(error) conditionMessage(error))
  stopifnot(!is.null(message), grepl(pattern, message, fixed = TRUE))
}

fixture <- arm_c_fixture()
alignment <- with(fixture, arm_c_align(student_data, aytm_data, mapping))
stopifnot(is.data.frame(alignment), nrow(alignment) == 42L,
  !anyNA(alignment), !anyDuplicated(alignment$student_column),
  identical(alignment$student_column, names(fixture$student_data)),
  sum(fixture$mapping$student_column %in% names(fixture$student_data)) == 23L,
  nrow(fixture$student_data) == 256L,
  identical(arm_c_number("5 - Extremely appealing"), 5),
  identical(arm_c_number(c("1: Low", "2 – Fair", "3", "4 - Good", "5 - Extremely appealing")), as.numeric(1:5)))
wrong_aliases <- fixture$mapping
wrong_aliases$student_column <- "never join this column"
stopifnot(identical(alignment, arm_c_align(fixture$student_data, fixture$aytm_data, wrong_aliases)))
assert_error(arm_c_align(fixture$student_data[-1L], fixture$aytm_data, fixture$mapping), "incomplete or ambiguous")
assert_error(arm_c_match_columns("q1", c("Q1: a", "Q1: b")), "incomplete or ambiguous")
stopifnot(identical(arm_c_match_columns(c("q1", "q11"), c("Q11: b", "Q1: a")), c(2L, 1L)))

harmonized <- with(fixture, arm_c_harmonize(student_data, aytm_data, alignment))
for (id in c("Age", "Income")) {
  left <- harmonized$student[[id]]
  right <- harmonized$aytm[[id]]
  stopifnot(length(left) == 256L, length(right) == 600L, !anyNA(left), !anyNA(right),
    length(unique(left)) >= 5L, identical(levels(factor(left)), levels(factor(right))))
}
stopifnot(identical(harmonized$aytm$Q1, rep(as.numeric(1:5), 120L)),
  sum(harmonized$audit$question_type == "continuous") == 36L,
  identical(arm_c_income(c(100000, 150000)), rep("$100,000-$199,999", 2L)),
  is.na(arm_c_income("Prefer not to say")))
assert_error(arm_c_income("unknown"), "could not be harmonized")
assert_error(arm_c_age("17"), "could not be harmonized")
stopifnot(all(is.na(arm_c_age(c(NA_character_, "", "  ")))))

# Missing demographic and screening answers must survive category collapsing as missing.
missing_fixture <- fixture
for (id in c("Age", "Gender", "PQ1")) {
  missing_fixture$student_data[[alignment$student_column[alignment$question_id == id]]][1:3] <-
    c(NA_character_, "", "  ")
  missing_fixture$aytm_data[[alignment$aytm_column[alignment$question_id == id]]][1:3] <-
    c(NA_character_, "", "  ")
}
missing_coded <- with(missing_fixture, arm_c_harmonize(student_data, aytm_data, alignment))
for (id in c("Age", "Gender", "PQ1")) {
  stopifnot(all(is.na(missing_coded$student[[id]][1:3])),
    all(is.na(missing_coded$aytm[[id]][1:3])))
}
missing_result <- do.call(run_arm_c, missing_fixture)
stopifnot(identical(missing_result$draw_n, 256L),
  identical(missing_result$calibration_audit$observed_supported_n, c(253L, 253L, 256L)),
  all(missing_result$battery$audit$real_missing[
    missing_result$battery$audit$question_id %in% c("Age", "Gender", "PQ1")] == 3L))
bad_scale <- fixture$aytm_data
bad_scale[[alignment$aytm_column[[7L]]]][[1L]] <- "6 - invalid"
assert_error(arm_c_harmonize(fixture$student_data, bad_scale, alignment), "unsupported values")
excluded_alignment <- alignment
excluded_alignment$notes[7:8] <- c("multi-select", "open-ended")
excluded <- arm_c_harmonize(fixture$student_data, fixture$aytm_data, excluded_alignment)
stopifnot(sum(excluded$audit$question_type == "excluded") == 2L,
  !any(c("Q1", "Q2") %in% names(excluded$student)))

set.seed(11)
result_one <- do.call(run_arm_c, fixture)
for (frame in c(result_one[c("synthetic", "margin_audit", "question_audit", "calibration_audit")],
  result_one$battery[c("results", "equivalence", "audit")])) {
  stopifnot(is.data.frame(frame), nrow(frame) > 0L, ncol(frame) > 0L)
}
set.seed(99)
result_two <- do.call(run_arm_c, c(fixture, list(seed = ARM_C_SEED)))
stopifnot(is.list(result_one), identical(result_one$seed, ARM_C_SEED),
  identical(result_one$draw_n, 256L), nrow(result_one$synthetic) == 256L,
  !anyDuplicated(result_one$synthetic$donor_id), identical(result_one, result_two),
  nrow(result_one$margin_audit) == 13L,
  all(result_one$margin_audit$selected_n == result_one$margin_audit$target_n),
  nrow(result_one$question_audit) == 42L, nrow(result_one$battery$results) == 42L,
  nrow(result_one$battery$equivalence) > 42L,
  nrow(result_one$calibration_audit) == 3L,
  all(result_one$calibration_audit$observed_supported_n == 256L))
changed_seed <- do.call(run_arm_c, c(fixture, list(seed = ARM_C_SEED + 1L)))
stopifnot(nrow(changed_seed$synthetic) == 256L,
  !identical(result_one$synthetic$donor_id, changed_seed$synthetic$donor_id))
bad <- fixture
bad$student_data <- bad$student_data[-1L, ]
assert_error(do.call(run_arm_c, bad), "expected_student_rows")
bad <- fixture
bad$synthetic_data$synthetic_id[[1L]] <- "wrong"
assert_error(do.call(run_arm_c, bad), "IDs must match")
bad <- fixture
bad$registry <- bad$registry[-1L, ]
assert_error(do.call(run_arm_c, bad), "every quantitative matched question")
bad <- fixture
bad$registry$question_type[[7L]] <- "categorical"
assert_error(do.call(run_arm_c, bad), "types must follow")

# Missing items and constant items must leave an explicit audit, while estimable items run.
partial_real <- harmonized$student
partial_real$Q1[1:2] <- NA_real_
partial_real$Q2 <- 1
partial_synthetic <- fixture$synthetic_data
partial_synthetic$Q2 <- 1
partial <- arm_c_compare(partial_real, partial_synthetic,
  fixture$registry[fixture$registry$question_id %in% c("Q1", "Q2"), ])
stopifnot(is.data.frame(partial$results), nrow(partial$results) == 1L,
  identical(partial$results$question_id, "Q1"),
  identical(partial$audit$real_missing, c(2L, 0L)),
  identical(partial$audit$status[[1L]], "Tested"),
  grepl("Not estimable", partial$audit$status[[2L]], fixed = TRUE))

# Unsupported calibration responses stay in the sample; fractional targets get integer quotas.
unsupported <- fixture
unsupported$student_data[[alignment$student_column[[2L]]]][[1L]] <- "Other"
rounded <- do.call(run_arm_c, unsupported)
stopifnot(identical(rounded$draw_n, 256L), is.data.frame(rounded$calibration_audit),
  identical(rounded$calibration_audit$observed_supported_n, c(256L, 255L, 256L)),
  is.data.frame(rounded$margin_audit), nrow(rounded$margin_audit) == 13L,
  all(rounded$margin_audit$selected_n == rounded$margin_audit$target_n))

# Inspect actual emitted markup, not source comments or the limitations vector alone.
report_path <- tempfile(fileext = ".html")
writeLines(render_arm_c_report(result_one), report_path)
report_text <- paste(readLines(report_path, warn = FALSE), collapse = "\n")
stopifnot(nchar(report_text) > 1000L,
  grepl("Student PQ1 includes No", report_text, fixed = TRUE),
  grepl("AYTM screened No out before fielding", report_text, fixed = TRUE),
  grepl("samples are screened differently", report_text, fixed = TRUE),
  grepl("AYTM is a national panel", report_text, fixed = TRUE),
  grepl("Southern-California-based", report_text, fixed = TRUE),
  grepl("Geography cannot be controlled for because the student survey never asked for it", report_text, fixed = TRUE),
  grepl("Arm C registered tests", report_text, fixed = TRUE))
unlink(report_path)

# Local integration: never print CSV contents, headers, values, or data-bearing errors.
# A checkout without the private inputs still runs the invented-fixture checks above.
private_paths <- file.path(ARM_C_DATA_DIRECTORY,
  c("student_CLEAN.csv", "aytm_CLEAN.csv", "Question_Mapping.csv"))
if (all(file.exists(private_paths))) {
  private_stage <- "read inputs"
  private_ok <- tryCatch(local({
    frames <- lapply(private_paths, utils::read.csv, check.names = FALSE, stringsAsFactors = FALSE)
    student <- frames[[1L]]; aytm <- frames[[2L]]; mapping <- frames[[3L]]
    matched <- mapping[tolower(trimws(mapping$match_status)) == "matched", , drop = FALSE]
    private_stage <<- "row and mapping counts"
    stopifnot(nrow(student) == 256L, nrow(aytm) == 600L, nrow(matched) == 42L,
      length(matched$student_column) == 42L,
      sum(matched$student_column %in% names(student)) < 42L)
    private_stage <<- "prefix alignment"
    joined <- arm_c_align(student, aytm, mapping)
    stopifnot(is.data.frame(joined), nrow(joined) == 42L, !anyNA(joined$student_column),
      !anyDuplicated(joined$student_column), all(startsWith(joined$student_column, "aytm:")))
    private_stage <<- "harmonization"
    coded <- arm_c_harmonize(student, aytm, joined)
    for (pattern in c("^Age$", "income")) {
      private_stage <<- paste("demographic levels", pattern)
      ids <- joined$question_id[grepl(pattern, joined$question_id, ignore.case = TRUE)]
      stopifnot(length(ids) == 1L)
      left <- coded$student[[ids[[1L]]]]; right <- coded$aytm[[ids[[1L]]]]
      stopifnot(length(left) == 256L, length(right) == 600L,
        length(unique(na.omit(left))) >= 5L,
        identical(levels(factor(left)), levels(factor(right))))
    }
    TRUE
  }), error = function(error) FALSE)
  if (!private_ok) stop(paste("Arm C private integration failed at", private_stage, "(contents suppressed)"))
  cat("test_arm_c.R: private CSV integration PASS (contents suppressed)\n")
} else {
  cat("test_arm_c.R: SKIP private CSV integration (inputs unavailable)\n")
}
cat("test_arm_c.R: PASS\n")
