#!/usr/bin/env Rscript

test_battery_repo_root <- function() {
  sourced_files <- vapply(sys.frames(), function(frame) {
    if (is.character(frame$ofile) && length(frame$ofile) > 0L) frame$ofile[[1L]] else NA_character_
  }, character(1L))
  sourced_files <- sourced_files[!is.na(sourced_files)]
  runner_files <- sourced_files[basename(sourced_files) == "run_test_battery.R"]
  if (length(runner_files) > 0L) {
    return(dirname(dirname(normalizePath(tail(runner_files, 1L), mustWork = TRUE))))
  }

  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 0L) {
    return(normalizePath(".", mustWork = TRUE))
  }
  dirname(dirname(normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)))
}

if (!exists("run_test_battery", envir = environment(), mode = "function", inherits = FALSE)) {
  source(
    file.path(test_battery_repo_root(), "analysis", "R", "test_battery.R"),
    local = environment()
  )
}

test_battery_usage <- function() {
  paste(
    "Usage: Rscript analysis/run_test_battery.R",
    "--real PATH --synthetic PATH --registry PATH",
    "--real-id COLUMN --synthetic-id COLUMN [--output PATH]"
  )
}

parse_test_battery_arguments <- function(arguments) {
  if (length(arguments) %% 2L != 0L) {
    stop(test_battery_usage())
  }
  parsed <- list()
  if (length(arguments) > 0L) {
    for (index in seq(1L, length(arguments), by = 2L)) {
      name <- arguments[[index]]
      if (!startsWith(name, "--")) {
        stop(test_battery_usage())
      }
      key <- substring(name, 3L)
      if (key %in% names(parsed)) {
        stop(sprintf("Argument --%s was supplied more than once.", key))
      }
      parsed[[key]] <- arguments[[index + 1L]]
    }
  }

  required <- c("real", "synthetic", "registry", "real-id", "synthetic-id")
  missing <- setdiff(required, names(parsed))
  if (length(missing) > 0L) {
    stop(sprintf(
      "Missing required arguments: %s\n%s",
      paste(missing, collapse = ", "),
      test_battery_usage()
    ))
  }
  unknown <- setdiff(names(parsed), c(required, "output"))
  if (length(unknown) > 0L) {
    stop(sprintf("Unknown arguments: %s\n%s", paste(unknown, collapse = ", "), test_battery_usage()))
  }
  parsed$output <- parsed$output %||% file.path("analysis", "output", "test_battery")
  parsed
}

`%||%` <- function(value, fallback) {
  if (is.null(value)) fallback else value
}

write_test_battery_results <- function(result, output_directory, sources = NULL) {
  dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  utils::write.csv(result$results, file.path(output_directory, "test_results.csv"), row.names = FALSE)
  utils::write.csv(result$equivalence, file.path(output_directory, "tost_details.csv"), row.names = FALSE)
  utils::write.csv(
    result$registry,
    file.path(output_directory, "registered_questions.csv"),
    row.names = FALSE,
    na = ""
  )

  provenance <- c(
    "NEO SMART VALIDATION — P4.5 TEST BATTERY",
    sprintf("Conventional two-sided confidence level: %.2f", result$confidence_level),
    sprintf("TOST alpha: %.2f; equivalence confidence level: %.2f", result$alpha, 1 - 2 * result$alpha),
    sprintf("Categorical Cramer's V bootstrap standard-error CI: %d replicates; fixed R seed: %d", result$bootstrap_replicates, result$seed),
    "Test routing: continuous = Welch t-test; binary = two-sample Wald z-test; categorical = Pearson chi-square",
    "Equivalence margins come only from the supplied question registry and are copied to registered_questions.csv",
    "Categorical equivalence requires every category's real-minus-synthetic proportion difference to pass TOST",
    "Outputs contain aggregate statistics and the question registry only; respondent-level real answers are not written",
    "Execution: local R only; no model, prompt, or provider call"
  )
  if (!is.null(sources)) {
    provenance <- c(
      provenance,
      sprintf("Real source: %s", sources$real),
      sprintf("Synthetic source: %s", sources$synthetic),
      sprintf("Registry source: %s", sources$registry),
      sprintf("Registry MD5 at analysis time: %s", unname(tools::md5sum(sources$registry)))
    )
  }
  writeLines(provenance, file.path(output_directory, "provenance.txt"))
}

test_battery_main <- function(arguments = commandArgs(trailingOnly = TRUE)) {
  options <- parse_test_battery_arguments(arguments)
  input_paths <- unlist(options[c("real", "synthetic", "registry")], use.names = TRUE)
  missing <- input_paths[!file.exists(input_paths)]
  if (length(missing) > 0L) {
    stop(sprintf("Test battery input was not found: %s", paste(missing, collapse = ", ")))
  }

  registry <- utils::read.csv(options$registry, check.names = FALSE, stringsAsFactors = FALSE)
  real_data <- utils::read.csv(options$real, check.names = FALSE, stringsAsFactors = FALSE)
  synthetic_data <- utils::read.csv(options$synthetic, check.names = FALSE, stringsAsFactors = FALSE)
  result <- run_test_battery(
    real_data,
    synthetic_data,
    registry,
    options[["real-id"]],
    options[["synthetic-id"]]
  )
  sources <- lapply(input_paths, normalizePath, mustWork = TRUE)
  write_test_battery_results(result, options$output, sources)
  cat(sprintf(
    "Ran the registered test battery for %d questions and wrote aggregate outputs to %s.\n",
    nrow(result$results),
    options$output
  ))
  invisible(result)
}

if (sys.nframe() == 0L) {
  test_battery_main()
}
