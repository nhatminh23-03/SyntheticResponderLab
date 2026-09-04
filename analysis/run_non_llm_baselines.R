#!/usr/bin/env Rscript

script_repo_root <- function() {
  sourced_files <- vapply(sys.frames(), function(frame) {
    if (is.character(frame$ofile) && length(frame$ofile) > 0L) {
      frame$ofile[[1L]]
    } else {
      NA_character_
    }
  }, character(1L))
  sourced_files <- sourced_files[!is.na(sourced_files)]
  runner_files <- sourced_files[basename(sourced_files) == "run_non_llm_baselines.R"]
  if (length(runner_files) > 0L) {
    script_path <- normalizePath(tail(runner_files, 1L), mustWork = TRUE)
    return(dirname(dirname(script_path)))
  }

  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 0L) {
    return(normalizePath(".", mustWork = TRUE))
  }
  script_path <- normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)
  dirname(dirname(script_path))
}

if (!exists("run_non_llm_baselines", envir = environment(), mode = "function", inherits = FALSE)) {
  source(
    file.path(script_repo_root(), "analysis", "R", "non_llm_baselines.R"),
    local = environment()
  )
}

usage <- function() {
  paste(
    "Usage: Rscript analysis/run_non_llm_baselines.R",
    "--input PATH --id COLUMN --items Q1,...,Q32",
    "--strata COLUMN,... --knn COLUMN,... [--output PATH] [--seed N] [--k N]"
  )
}

parse_arguments <- function(arguments) {
  if (length(arguments) %% 2L != 0L) {
    stop(usage())
  }
  parsed <- list()
  if (length(arguments) > 0L) {
    for (index in seq(1L, length(arguments), by = 2L)) {
      name <- arguments[[index]]
      if (!startsWith(name, "--")) {
        stop(usage())
      }
      key <- substring(name, 3L)
      if (key %in% names(parsed)) {
        stop(sprintf("Argument --%s was supplied more than once.", key))
      }
      parsed[[key]] <- arguments[[index + 1L]]
    }
  }

  required <- c("input", "id", "items", "strata", "knn")
  missing <- setdiff(required, names(parsed))
  if (length(missing) > 0L) {
    stop(sprintf("Missing required arguments: %s\n%s", paste(missing, collapse = ", "), usage()))
  }
  unknown <- setdiff(names(parsed), c(required, "output", "seed", "k"))
  if (length(unknown) > 0L) {
    stop(sprintf("Unknown arguments: %s\n%s", paste(unknown, collapse = ", "), usage()))
  }

  split_columns <- function(value) {
    columns <- trimws(strsplit(value, ",", fixed = TRUE)[[1L]])
    columns[nzchar(columns)]
  }
  parsed$items <- split_columns(parsed$items)
  parsed$strata <- split_columns(parsed$strata)
  parsed$knn <- split_columns(parsed$knn)
  parsed$output <- parsed$output %||% file.path("analysis", "output", "non_llm_baselines")
  parsed$seed <- as.integer(parsed$seed %||% 20260904L)
  parsed$k <- as.integer(parsed$k %||% 5L)
  if (is.na(parsed$seed) || is.na(parsed$k)) {
    stop("--seed and --k must be integers.")
  }
  parsed
}

`%||%` <- function(value, fallback) {
  if (is.null(value)) fallback else value
}

write_baseline_results <- function(result, output_directory) {
  dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  for (method in names(result$predictions)) {
    output <- result$predictions[[method]]
    output$evaluation_id <- sprintf("heldout_%03d", seq_len(nrow(output)))
    utils::write.csv(
      output,
      file.path(output_directory, paste0(method, ".csv")),
      row.names = FALSE
    )
  }
  utils::write.csv(result$metrics, file.path(output_directory, "metrics.csv"), row.names = FALSE)
  utils::write.csv(result$audit, file.path(output_directory, "held_out_audit.csv"), row.names = FALSE)
}

main <- function(arguments = commandArgs(trailingOnly = TRUE)) {
  options <- parse_arguments(arguments)
  if (!file.exists(options$input)) {
    stop(sprintf("Input CSV was not found: %s", options$input))
  }
  real_data <- utils::read.csv(options$input, check.names = FALSE, stringsAsFactors = FALSE)
  result <- run_non_llm_baselines(
    real_data = real_data,
    id_column = options$id,
    item_columns = options$items,
    stratum_columns = options$strata,
    knn_columns = options$knn,
    seed = options$seed,
    k = options$k
  )
  write_baseline_results(result, options$output)
  cat(sprintf(
    "Wrote five held-out baselines to %s (fit: %d; evaluation: %d; overlap: %d).\n",
    options$output,
    result$audit$fit_rows[[1L]],
    result$audit$evaluation_rows[[1L]],
    sum(result$audit$overlap_rows)
  ))
  invisible(result)
}

if (sys.nframe() == 0L) {
  main()
}
