#!/usr/bin/env Rscript

arm_b_repo_root <- function() {
  sourced_files <- vapply(sys.frames(), function(frame) {
    if (is.character(frame$ofile) && length(frame$ofile) > 0L) frame$ofile[[1L]] else NA_character_
  }, character(1L))
  sourced_files <- sourced_files[!is.na(sourced_files)]
  runner_files <- sourced_files[basename(sourced_files) == "run_arm_b.R"]
  if (length(runner_files) > 0L) {
    return(dirname(dirname(normalizePath(tail(runner_files, 1L), mustWork = TRUE))))
  }

  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 0L) {
    return(normalizePath(".", mustWork = TRUE))
  }
  dirname(dirname(normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)))
}

arm_b_root <- arm_b_repo_root()
if (!exists("read_parquet_frame", envir = environment(), mode = "function", inherits = FALSE)) {
  source(file.path(arm_b_root, "analysis", "screen_counts.R"), local = environment())
}
if (!exists("run_arm_b", envir = environment(), mode = "function", inherits = FALSE)) {
  source(file.path(arm_b_root, "analysis", "R", "arm_b.R"), local = environment())
}

arm_b_usage <- function() {
  paste(
    "Usage: Rscript analysis/run_arm_b.R",
    "--housing PATH --person PATH --real PATH [--output PATH]"
  )
}

parse_arm_b_arguments <- function(arguments) {
  if (length(arguments) %% 2L != 0L) {
    stop(arm_b_usage())
  }
  parsed <- list()
  if (length(arguments) > 0L) {
    for (index in seq(1L, length(arguments), by = 2L)) {
      name <- arguments[[index]]
      if (!startsWith(name, "--")) {
        stop(arm_b_usage())
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
    stop(sprintf("Missing required arguments: %s\n%s", paste(missing, collapse = ", "), arm_b_usage()))
  }
  unknown <- setdiff(names(parsed), c(required, "output"))
  if (length(unknown) > 0L) {
    stop(sprintf("Unknown arguments: %s\n%s", paste(unknown, collapse = ", "), arm_b_usage()))
  }
  parsed$output <- parsed$output %||% file.path("analysis", "output", "arm_b")
  parsed
}

write_arm_b_results <- function(result, output_directory, sources = NULL) {
  dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  utils::write.csv(
    result$synthetic,
    file.path(output_directory, "synthetic_respondents.csv"),
    row.names = FALSE
  )
  utils::write.csv(result$margin_audit, file.path(output_directory, "margin_audit.csv"), row.names = FALSE)
  utils::write.csv(result$convergence, file.path(output_directory, "ipf_convergence.csv"), row.names = FALSE)
  utils::write.csv(result$frame_audit, file.path(output_directory, "frame_audit.csv"), row.names = FALSE)

  provenance <- c(
    "NEO SMART VALIDATION — ARM B",
    sprintf("Fixed R seed: %d", result$seed),
    sprintf("Synthetic draw: %d unique PUMS householders, without replacement", result$draw_n),
    sprintf("Eligible PUMS source frame: %d adult householders", result$source_frame_n),
    sprintf("IPF matching margins: %s", paste(result$match_characteristics, collapse = ", ")),
    "Starting weights: ACS WGTP; IPF tolerance and convergence history are written with the outputs",
    "Final draw: quota-balanced without replacement to reproduce every observed marginal count exactly",
    "Real input use: completed respondents' demographics only; survey answers and individual real rows are not written",
    "Geographic support: a California-only PUMS frame cannot match the national real panel and is rejected",
    "Execution: local R only; no model, prompt, or provider call"
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

arm_b_main <- function(arguments = commandArgs(trailingOnly = TRUE)) {
  options <- parse_arm_b_arguments(arguments)
  input_paths <- unlist(options[c("housing", "person", "real")], use.names = TRUE)
  missing <- input_paths[!file.exists(input_paths)]
  if (length(missing) > 0L) {
    stop(sprintf("Arm B input was not found: %s", paste(missing, collapse = ", ")))
  }

  housing <- read_parquet_frame(options$housing)
  person <- read_parquet_frame(options$person)
  real_data <- read_arm_b_real_demographics(options$real)
  result <- run_arm_b(housing, person, real_data)
  sources <- lapply(input_paths, normalizePath, mustWork = TRUE)
  write_arm_b_results(result, options$output, sources)
  cat(sprintf(
    "Arm B drew %d distribution-matched synthetic respondents with fixed seed %d and wrote outputs to %s.\n",
    result$draw_n,
    result$seed,
    options$output
  ))
  invisible(result)
}

if (sys.nframe() == 0L) {
  arm_b_main()
}
