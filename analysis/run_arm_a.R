#!/usr/bin/env Rscript

arm_a_repo_root <- function() {
  sourced_files <- vapply(sys.frames(), function(frame) {
    if (is.character(frame$ofile) && length(frame$ofile) > 0L) frame$ofile[[1L]] else NA_character_
  }, character(1L))
  sourced_files <- sourced_files[!is.na(sourced_files)]
  runner_files <- sourced_files[basename(sourced_files) == "run_arm_a.R"]
  if (length(runner_files) > 0L) {
    return(dirname(dirname(normalizePath(tail(runner_files, 1L), mustWork = TRUE))))
  }

  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 0L) {
    return(normalizePath(".", mustWork = TRUE))
  }
  dirname(dirname(normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)))
}

arm_a_root <- arm_a_repo_root()
if (!exists("screen_pums_frames", envir = environment(), mode = "function", inherits = FALSE)) {
  source(file.path(arm_a_root, "analysis", "screen_counts.R"), local = environment())
}
if (!exists("run_arm_a", envir = environment(), mode = "function", inherits = FALSE)) {
  source(file.path(arm_a_root, "analysis", "R", "arm_a.R"), local = environment())
}

arm_a_usage <- function() {
  paste(
    "Usage: Rscript analysis/run_arm_a.R",
    "--housing PATH --person PATH --real PATH [--output PATH]"
  )
}

parse_arm_a_arguments <- function(arguments) {
  if (length(arguments) %% 2L != 0L) {
    stop(arm_a_usage())
  }
  parsed <- list()
  if (length(arguments) > 0L) {
    for (index in seq(1L, length(arguments), by = 2L)) {
      name <- arguments[[index]]
      if (!startsWith(name, "--")) {
        stop(arm_a_usage())
      }
      key <- substring(name, 3L)
      if (key %in% names(parsed)) {
        stop(sprintf("Argument --%s was supplied more than once.", key))
      }
      parsed[[key]] <- arguments[[index + 1L]]
    }
  }

  required <- c("housing", "person", "real")
  missing <- setdiff(required, names(parsed))
  if (length(missing) > 0L) {
    stop(sprintf("Missing required arguments: %s\n%s", paste(missing, collapse = ", "), arm_a_usage()))
  }
  unknown <- setdiff(names(parsed), c(required, "output"))
  if (length(unknown) > 0L) {
    stop(sprintf("Unknown arguments: %s\n%s", paste(unknown, collapse = ", "), arm_a_usage()))
  }
  parsed$output <- parsed$output %||% file.path("analysis", "output", "arm_a")
  parsed
}

write_arm_a_results <- function(result, output_directory, sources = NULL) {
  dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  utils::write.csv(
    result$synthetic,
    file.path(output_directory, "synthetic_respondents.csv"),
    row.names = FALSE
  )
  utils::write.csv(result$comparison, file.path(output_directory, "comparison.csv"), row.names = FALSE)
  utils::write.csv(result$age_summary, file.path(output_directory, "age_summary.csv"), row.names = FALSE)
  utils::write.csv(result$screen_audit, file.path(output_directory, "screen_audit.csv"), row.names = FALSE)
  utils::write.csv(result$funnel, file.path(output_directory, "screen_funnel.csv"), row.names = FALSE)

  provenance <- c(
    "NEO SMART VALIDATION — ARM A",
    sprintf("Fixed R seed: %d", result$seed),
    sprintf("Synthetic draw: %d respondents, WGTP-weighted without replacement", result$draw_n),
    "Hard screens: ACS BLD=02; HINCP x ADJINC / 1,000,000 >= $100,000; householder AGEP 30-65 inclusive",
    "Real comparison: completed AYTM respondents only; individual real rows and survey answers are not written",
    "Execution: local R only; no model or provider calls"
  )
  if (!is.null(sources)) {
    provenance <- c(
      provenance,
      sprintf("Housing source: %s", sources$housing),
      sprintf("Person source: %s", sources$person),
      sprintf("Real source: %s", sources$real)
    )
  }
  writeLines(provenance, file.path(output_directory, "provenance.txt"))
}

arm_a_main <- function(arguments = commandArgs(trailingOnly = TRUE)) {
  options <- parse_arm_a_arguments(arguments)
  input_paths <- unlist(options[c("housing", "person", "real")], use.names = TRUE)
  missing <- input_paths[!file.exists(input_paths)]
  if (length(missing) > 0L) {
    stop(sprintf("Arm A input was not found: %s", paste(missing, collapse = ", ")))
  }

  housing <- read_parquet_frame(options$housing)
  person <- read_parquet_frame(options$person)
  real_data <- utils::read.csv(options$real, check.names = FALSE, stringsAsFactors = FALSE)
  result <- run_arm_a(housing, person, real_data)
  sources <- lapply(input_paths, normalizePath, mustWork = TRUE)
  write_arm_a_results(result, options$output, sources)
  cat(sprintf(
    "Arm A drew %d screened synthetic respondents with fixed seed %d and wrote aggregate comparison outputs to %s.\n",
    result$draw_n,
    result$seed,
    options$output
  ))
  invisible(result)
}

if (sys.nframe() == 0L) {
  arm_a_main()
}
