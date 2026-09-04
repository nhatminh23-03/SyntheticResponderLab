#!/usr/bin/env Rscript

run_all_repo_root <- function() {
  sourced_files <- vapply(sys.frames(), function(frame) {
    if (is.character(frame$ofile) && length(frame$ofile) > 0L) frame$ofile[[1L]] else NA_character_
  }, character(1L))
  sourced_files <- sourced_files[!is.na(sourced_files)]
  runner_files <- sourced_files[basename(sourced_files) == "run_all.R"]
  if (length(runner_files) > 0L) {
    return(dirname(dirname(normalizePath(tail(runner_files, 1L), mustWork = TRUE))))
  }

  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 0L) {
    return(normalizePath(".", mustWork = TRUE))
  }
  dirname(dirname(normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)))
}

run_all_root <- run_all_repo_root()
source(file.path(run_all_root, "analysis", "screen_counts.R"), local = environment())
source(file.path(run_all_root, "analysis", "R", "arm_a.R"), local = environment())
source(file.path(run_all_root, "analysis", "R", "arm_b.R"), local = environment())
source(file.path(run_all_root, "analysis", "R", "non_llm_baselines.R"), local = environment())
source(file.path(run_all_root, "analysis", "R", "test_battery.R"), local = environment())
source(file.path(run_all_root, "analysis", "R", "report.R"), local = environment())

run_all_usage <- function() {
  paste(
    "Usage: Rscript analysis/run_all.R",
    "[--arm-a-housing PATH] [--arm-a-person PATH]",
    "[--arm-b-housing PATH] [--arm-b-person PATH]",
    "[--real PATH] [--synthetic PATH] [--registry PATH]",
    "[--real-id COLUMN] [--synthetic-id COLUMN]",
    "[--strata COLUMN,...] [--knn COLUMN,...] [--output PATH]"
  )
}

run_all_split_columns <- function(value, label) {
  columns <- trimws(strsplit(value, ",", fixed = TRUE)[[1L]])
  columns <- columns[nzchar(columns)]
  if (length(columns) == 0L || anyDuplicated(columns)) {
    stop(sprintf("%s must name one or more unique comma-separated columns.", label))
  }
  columns
}

parse_run_all_arguments <- function(arguments, repo_root = run_all_root) {
  if (length(arguments) %% 2L != 0L) {
    stop(run_all_usage())
  }
  parsed <- list()
  if (length(arguments) > 0L) {
    for (index in seq(1L, length(arguments), by = 2L)) {
      name <- arguments[[index]]
      if (!startsWith(name, "--")) {
        stop(run_all_usage())
      }
      key <- substring(name, 3L)
      if (key %in% names(parsed)) {
        stop(sprintf("Argument --%s was supplied more than once.", key))
      }
      parsed[[key]] <- arguments[[index + 1L]]
    }
  }

  allowed <- c(
    "arm-a-housing", "arm-a-person", "arm-b-housing", "arm-b-person", "real",
    "synthetic", "registry", "real-id", "synthetic-id", "strata", "knn", "output"
  )
  unknown <- setdiff(names(parsed), allowed)
  if (length(unknown) > 0L) {
    stop(sprintf("Unknown arguments: %s\n%s", paste(unknown, collapse = ", "), run_all_usage()))
  }

  data_directory <- file.path(repo_root, "analysis", "data")
  parsed[["arm-a-housing"]] <- parsed[["arm-a-housing"]] %||%
    file.path(data_directory, "arm_a_housing.parquet")
  parsed[["arm-a-person"]] <- parsed[["arm-a-person"]] %||%
    file.path(data_directory, "arm_a_person.parquet")
  parsed[["arm-b-housing"]] <- parsed[["arm-b-housing"]] %||%
    file.path(data_directory, "arm_b_housing.parquet")
  parsed[["arm-b-person"]] <- parsed[["arm-b-person"]] %||%
    file.path(data_directory, "arm_b_person.parquet")
  parsed$real <- parsed$real %||% file.path(data_directory, "real_responses.csv")
  parsed$synthetic <- parsed$synthetic %||% file.path(data_directory, "synthetic_responses.csv")
  parsed$registry <- parsed$registry %||% file.path(data_directory, "question_registry.csv")
  parsed[["real-id"]] <- parsed[["real-id"]] %||% "Response ID"
  parsed[["synthetic-id"]] <- parsed[["synthetic-id"]] %||% "synthetic_id"
  parsed$strata <- run_all_split_columns(
    parsed$strata %||% "Gender,Household Income,State",
    "--strata"
  )
  parsed$knn <- run_all_split_columns(
    parsed$knn %||% "Age,Gender,Household Income,State",
    "--knn"
  )
  parsed$output <- parsed$output %||%
    file.path(repo_root, "analysis", "output", "validation_report.html")
  if (tolower(tools::file_ext(parsed$output)) != "html") {
    stop("--output must end in .html.")
  }
  parsed
}

read_run_all_pums <- function(path) {
  if (tolower(tools::file_ext(path)) == "csv") {
    return(utils::read.csv(path, check.names = FALSE, stringsAsFactors = FALSE))
  }
  read_parquet_frame(path)
}

run_all_main <- function(arguments = commandArgs(trailingOnly = TRUE)) {
  options <- parse_run_all_arguments(arguments)
  input_paths <- c(
    arm_a_housing = options[["arm-a-housing"]],
    arm_a_person = options[["arm-a-person"]],
    arm_b_housing = options[["arm-b-housing"]],
    arm_b_person = options[["arm-b-person"]],
    real_responses = options$real,
    synthetic_responses = options$synthetic,
    question_registry = options$registry
  )
  manifest <- report_input_manifest(input_paths)

  arm_a_housing <- read_run_all_pums(options[["arm-a-housing"]])
  arm_a_person <- read_run_all_pums(options[["arm-a-person"]])
  arm_b_housing <- read_run_all_pums(options[["arm-b-housing"]])
  arm_b_person <- read_run_all_pums(options[["arm-b-person"]])
  real_data <- utils::read.csv(options$real, check.names = FALSE, stringsAsFactors = FALSE)
  synthetic_data <- utils::read.csv(
    options$synthetic,
    check.names = FALSE,
    stringsAsFactors = FALSE
  )
  registry <- utils::read.csv(options$registry, check.names = FALSE, stringsAsFactors = FALSE)

  result <- run_validation_report_analyses(
    arm_a_housing,
    arm_a_person,
    arm_b_housing,
    arm_b_person,
    real_data,
    synthetic_data,
    registry,
    options[["real-id"]],
    options[["synthetic-id"]],
    options$strata,
    options$knn,
    manifest
  )
  write_validation_report(result, options$output)
  cat(sprintf(
    "Rebuilt all implemented validation arms and %d registered tests in %s.\n",
    nrow(result$battery$results),
    options$output
  ))
  invisible(result)
}

`%||%` <- function(value, fallback) {
  if (is.null(value)) fallback else value
}

if (sys.nframe() == 0L) {
  run_all_main()
}
