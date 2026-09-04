REPORT_BASELINE_SEED <- 20260904L
REPORT_KNN_K <- 5L

report_require_columns <- function(frame, columns, label) {
  missing <- setdiff(columns, names(frame))
  if (length(missing) > 0L) {
    stop(sprintf("%s is missing required columns: %s", label, paste(missing, collapse = ", ")))
  }
}

report_completed_responses <- function(real_data, expected_rows = 600L) {
  report_require_columns(real_data, "Status", "Real panel")
  status <- trimws(as.character(real_data$Status))
  completed <- real_data[!is.na(status) & status == "Completed", , drop = FALSE]
  if (nrow(completed) != expected_rows) {
    stop(sprintf(
      "Expected exactly %d completed real respondents for the report; found %d.",
      expected_rows,
      nrow(completed)
    ))
  }
  completed
}

report_input_manifest <- function(paths) {
  if (is.null(names(paths)) || any(names(paths) == "") || anyDuplicated(names(paths))) {
    stop("Report input paths must be uniquely named.")
  }
  missing <- paths[!file.exists(paths)]
  if (length(missing) > 0L) {
    stop(sprintf("Report input was not found: %s", paste(missing, collapse = ", ")))
  }

  normalized <- vapply(paths, normalizePath, character(1L), mustWork = TRUE)
  data.frame(
    input = names(normalized),
    file = basename(normalized),
    md5 = unname(tools::md5sum(normalized)),
    stringsAsFactors = FALSE
  )
}

report_seed_register <- function(baseline_names, question_n) {
  if (length(baseline_names) == 0L || any(is.na(baseline_names)) || any(baseline_names == "")) {
    stop("The report seed register requires named baseline methods.")
  }
  if (length(question_n) != 1L || is.na(question_n) || question_n < 1L ||
      question_n != as.integer(question_n)) {
    stop("The report seed register requires a positive integer question count.")
  }

  data.frame(
    analysis = c(
      "Arm A weighted draw",
      "Arm B balanced draw",
      "Non-LLM held-out split",
      paste("Non-LLM prediction:", baseline_names),
      "Categorical effect-size bootstrap"
    ),
    seed = c(
      as.character(ARM_A_SEED),
      as.character(ARM_B_SEED),
      as.character(REPORT_BASELINE_SEED),
      as.character(REPORT_BASELINE_SEED + seq_along(baseline_names)),
      sprintf(
        "%d + registry row index - 1 (rows 1-%d)",
        TEST_BATTERY_SEED,
        as.integer(question_n)
      )
    ),
    stringsAsFactors = FALSE
  )
}

run_validation_report_analyses <- function(
  arm_a_housing,
  arm_a_person,
  arm_b_housing,
  arm_b_person,
  real_data,
  synthetic_data,
  registry,
  real_id_column,
  synthetic_id_column,
  stratum_columns,
  knn_columns,
  input_manifest
) {
  registered <- validate_question_registry(registry)
  completed <- report_completed_responses(real_data, expected_rows = ARM_A_DRAW_N)

  arm_a <- run_arm_a(
    arm_a_housing,
    arm_a_person,
    real_data,
    real_id_column = real_id_column
  )
  arm_b <- run_arm_b(
    arm_b_housing,
    arm_b_person,
    real_data,
    real_id_column = real_id_column
  )
  baselines <- run_non_llm_baselines(
    real_data = completed,
    id_column = real_id_column,
    item_columns = registered$question_id,
    stratum_columns = stratum_columns,
    knn_columns = knn_columns,
    seed = REPORT_BASELINE_SEED,
    k = REPORT_KNN_K
  )
  battery <- run_test_battery(
    real_data = completed,
    synthetic_data = synthetic_data,
    registry = registered,
    real_id_column = real_id_column,
    synthetic_id_column = synthetic_id_column,
    seed = TEST_BATTERY_SEED
  )

  stopifnot(
    arm_a$seed == ARM_A_SEED,
    arm_b$seed == ARM_B_SEED,
    baselines$split$seed == REPORT_BASELINE_SEED,
    battery$seed == TEST_BATTERY_SEED,
    identical(baselines$audit$baseline, NON_LLM_BASELINES),
    all(baselines$audit$overlap_rows == 0L),
    nrow(battery$results) == nrow(registered),
    identical(battery$results$question_id, registered$question_id)
  )

  list(
    coverage = data.frame(
      component = c(
        "Arm A — hard-screened draw",
        "Arm B — distribution-matched draw",
        "Arm C — convenience-sample match",
        "Non-LLM response baselines",
        "Registered quantitative test battery"
      ),
      status = c("Complete", "Complete", "Blocked", "Complete", "Complete"),
      result = c(
        sprintf("%d screened respondents", arm_a$draw_n),
        sprintf("%d IPF-matched respondents", arm_b$draw_n),
        "Yufan Lin's approximately 300-person sample has not been received; no result is fabricated",
        sprintf("%d held-out methods; fit and evaluation N = %d/%d", nrow(baselines$audit), baselines$audit$fit_rows[[1L]], baselines$audit$evaluation_rows[[1L]]),
        sprintf("%d registered questions; all routed tests and TOST equivalence results reported", nrow(battery$results))
      ),
      stringsAsFactors = FALSE
    ),
    seeds = report_seed_register(NON_LLM_BASELINES, nrow(registered)),
    inputs = input_manifest,
    arm_a = arm_a,
    arm_b = arm_b,
    baselines = list(
      audit = baselines$audit,
      metrics = baselines$metrics
    ),
    battery = battery
  )
}

html_escape <- function(values) {
  escaped <- as.character(values)
  escaped[is.na(values)] <- ""
  escaped <- gsub("&", "&amp;", escaped, fixed = TRUE)
  escaped <- gsub("<", "&lt;", escaped, fixed = TRUE)
  escaped <- gsub(">", "&gt;", escaped, fixed = TRUE)
  escaped <- gsub('"', "&quot;", escaped, fixed = TRUE)
  gsub("'", "&#39;", escaped, fixed = TRUE)
}

format_report_values <- function(values) {
  if (is.logical(values)) {
    output <- ifelse(values, "Yes", "No")
    output[is.na(values)] <- "—"
    return(output)
  }
  if (is.numeric(values)) {
    output <- vapply(values, function(value) {
      if (is.na(value)) "—" else formatC(value, digits = 7L, format = "g")
    }, character(1L))
    return(output)
  }
  output <- as.character(values)
  output[is.na(values) | output == ""] <- "—"
  output
}

report_html_table <- function(frame, caption = NULL) {
  if (!is.data.frame(frame) || ncol(frame) == 0L) {
    stop("HTML report tables require a data frame with at least one column.")
  }
  header <- paste0("<th>", html_escape(names(frame)), "</th>", collapse = "")
  body <- if (nrow(frame) == 0L) {
    sprintf('<tr><td colspan="%d">No rows</td></tr>', ncol(frame))
  } else {
    paste(vapply(seq_len(nrow(frame)), function(index) {
      cells <- vapply(frame[index, , drop = FALSE], function(column) {
        html_escape(format_report_values(column[[1L]]))
      }, character(1L))
      paste0("<tr><td>", paste(cells, collapse = "</td><td>"), "</td></tr>")
    }, character(1L)), collapse = "\n")
  }
  caption_html <- if (is.null(caption)) "" else paste0("<caption>", html_escape(caption), "</caption>")
  paste0(
    '<div class="table-wrap"><table>', caption_html,
    "<thead><tr>", header, "</tr></thead><tbody>", body,
    "</tbody></table></div>"
  )
}

render_validation_report <- function(result) {
  test_columns <- c(
    "question_id", "question_type", "real_n", "synthetic_n", "test", "effect_size",
    "effect_estimate", "confidence_level", "confidence_lower", "confidence_upper",
    "standardized_effect_size", "standardized_effect_estimate",
    "standardized_confidence_lower", "standardized_confidence_upper", "statistic",
    "degrees_of_freedom", "p_value", "equivalence_margin", "tost_confidence_level",
    "tost_p_value", "equivalent", "assumption_note"
  )
  report_require_columns(result$battery$results, test_columns, "Report test results")

  lines <- c(
    "<!doctype html>",
    '<html lang="en">',
    "<head>",
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    "<title>Neo Smart Living validation report</title>",
    "<style>",
    ":root{color-scheme:light;--ink:#17202a;--muted:#5f6b76;--line:#d8dee4;--paper:#fff;--wash:#f5f7f9;--accent:#145a70}",
    "*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}",
    "main{max-width:1180px;margin:0 auto;padding:40px 24px 64px;background:var(--paper)}h1{font-size:2rem;margin:0 0 8px}h2{margin-top:42px;border-bottom:2px solid var(--accent);padding-bottom:6px}h3{margin-top:28px}.lede,.note{color:var(--muted);max-width:90ch}",
    ".table-wrap{overflow-x:auto;margin:14px 0 24px}table{border-collapse:collapse;width:100%;font-size:.86rem}caption{text-align:left;font-weight:700;padding:0 0 7px}th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}th{background:#eaf1f4;position:sticky;top:0}tbody tr:nth-child(even){background:#fafbfc}code{background:#edf1f3;padding:1px 4px;border-radius:3px}details{margin:12px 0}summary{cursor:pointer;font-weight:700}",
    "</style>",
    "</head>",
    "<body><main>",
    "<h1>Neo Smart Living validation report</h1>",
    paste0(
      '<p class="lede">A from-scratch, local R rebuild of the implemented validation arms and ',
      'registered quantitative tests. The report contains aggregate results only. It makes no ',
      'model or provider calls and never sends real survey answers to a prompt.</p>'
    ),
    "<h2>Coverage and limitations</h2>",
    report_html_table(result$coverage),
    paste0(
      '<p class="note"><strong>Scope boundary:</strong> interview theme validation and inter-rater ',
      'agreement belong to P4.7 and are not fabricated here. Arm C remains visibly blocked on its ',
      'external input.</p>'
    ),
    "<h2>Reproducibility register</h2>",
    "<p>The output has no wall-clock timestamp. Identical inputs and the pinned R environment produce the same HTML bytes.</p>",
    report_html_table(result$seeds, "Fixed seeds"),
    report_html_table(result$inputs, "Input files and checksums"),
    "<h2>Arm A — hard-screened draw</h2>",
    "<p>California detached single-family households with adjusted income of at least $100,000 and householder age 30–65; WGTP-weighted draw without replacement.</p>",
    report_html_table(result$arm_a$funnel, "Screen funnel"),
    report_html_table(result$arm_a$screen_audit, "Hard-screen comparison"),
    report_html_table(result$arm_a$age_summary, "Age summary"),
    "<details><summary>All Arm A demographic comparison rows</summary>",
    report_html_table(result$arm_a$comparison),
    "</details>",
    "<h2>Arm B — distribution-matched draw</h2>",
    "<p>Occupied adult householders raked from WGTP to observed age-band, gender, household-income-band, and state margins, followed by a quota-balanced draw without replacement.</p>",
    report_html_table(result$arm_b$frame_audit, "Source-frame audit"),
    report_html_table(result$arm_b$convergence, "IPF convergence"),
    "<details><summary>All Arm B target, raked, and selected margins</summary>",
    report_html_table(result$arm_b$margin_audit),
    "</details>",
    "<h2>Arm C — convenience-sample match</h2>",
    "<p class=\"note\">Blocked: Yufan Lin's approximately 300-person convenience sample has not been received. No Arm C statistics are imputed, copied from another arm, or presented as observed.</p>",
    "<h2>Non-LLM response baseline arm</h2>",
    "<p>All five methods are fit on one fixed half of the real panel and evaluated only on the disjoint held-out half.</p>",
    report_html_table(result$baselines$audit, "Held-out leakage audit"),
    report_html_table(result$baselines$metrics, "Held-out baseline metrics"),
    "<h2>Registered quantitative test battery</h2>",
    paste0(
      "<p>Every registered question is reported with its routed test, effect estimate, confidence interval, p-value, pre-registered equivalence margin, and TOST decision. ",
      "The configured synthetic response file is the comparison sample; the five non-LLM methods retain their held-out P4.6 metrics above.</p>"
    ),
    report_html_table(result$battery$results[, test_columns, drop = FALSE], "All registered question tests"),
    "<details><summary>All per-estimand TOST results</summary>",
    report_html_table(result$battery$equivalence),
    "</details>",
    "<h2>Method notes</h2>",
    "<ul><li>Continuous items: Welch two-sample t-test, raw mean difference, Hedges' g, and raw-unit TOST.</li><li>Binary items: two-sample unpooled Wald z-test, risk difference, and TOST.</li><li>Categorical items: Pearson chi-square, Cramer's V with fixed-seed bootstrap confidence interval, and category-wise TOST; equivalence requires every category to pass.</li><li>All equivalence margins come from the validated registry supplied before analysis.</li></ul>",
    "</main></body></html>"
  )
  paste(lines, collapse = "\n")
}

write_validation_report <- function(result, output_path) {
  if (length(output_path) != 1L || is.na(output_path) || !nzchar(output_path) ||
      tolower(tools::file_ext(output_path)) != "html") {
    stop("Report output must be one non-empty path ending in .html.")
  }
  output_directory <- dirname(output_path)
  dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  html <- render_validation_report(result)
  temporary <- tempfile(pattern = "validation-report-", tmpdir = output_directory, fileext = ".html")
  on.exit(if (file.exists(temporary)) unlink(temporary), add = TRUE)
  writeLines(html, temporary, useBytes = TRUE)
  if (!file.rename(temporary, output_path)) {
    if (!file.copy(temporary, output_path, overwrite = TRUE)) {
      stop(sprintf("Could not write validation report to %s.", output_path))
    }
    unlink(temporary)
  }
  invisible(output_path)
}
