#!/usr/bin/env Rscript

# Report the Census-screen funnel used by research/neo_persona_set/phase1/screen_and_draw.py.
#
# Preferred input is the pipeline's two slim PUMS parquet files. On branches where those generated
# files are absent, the script falls back to personas-B.csv and reports only facts recoverable from
# that already-screened final draw. It never treats the 30 selected personas as the source pool.

DETACHED_SINGLE_FAMILY <- 2
MIN_HOUSEHOLD_INCOME <- 100000
MIN_AGE <- 30
MAX_AGE <- 65
REFERENCE_PERSON <- 20
DEFAULT_DRAW_N <- 30
DEFAULT_SEED <- 20260825

as_number <- function(values) {
  suppressWarnings(as.numeric(as.character(values)))
}

require_columns <- function(frame, columns, label) {
  missing <- setdiff(columns, names(frame))
  if (length(missing) > 0L) {
    stop(sprintf("%s is missing required columns: %s", label, paste(missing, collapse = ", ")))
  }
}

weighted_total <- function(frame) {
  sum(as_number(frame$WGTP), na.rm = TRUE)
}

funnel_row <- function(stage, frame, detail = "") {
  data.frame(
    stage = stage,
    records = nrow(frame),
    weighted_households = weighted_total(frame),
    detail = detail,
    stringsAsFactors = FALSE
  )
}

weighted_draw <- function(pool, n = DEFAULT_DRAW_N, seed = DEFAULT_SEED) {
  if (length(n) != 1L || is.na(n) || n < 1 || n != as.integer(n)) {
    stop("Draw size must be a positive integer.")
  }
  if (nrow(pool) < n) {
    stop(sprintf("Eligible pool holds only %d records; cannot draw %d.", nrow(pool), n))
  }

  weights <- as_number(pool$WGTP)
  if (any(!is.finite(weights)) || any(weights <= 0)) {
    stop("Every eligible record must have a finite, positive WGTP.")
  }

  set.seed(seed)
  picks <- sample.int(nrow(pool), size = n, replace = FALSE, prob = weights)
  pool[picks, , drop = FALSE]
}

screen_pums_frames <- function(housing, person, draw_n = DEFAULT_DRAW_N, seed = DEFAULT_SEED) {
  require_columns(
    housing,
    c("SERIALNO", "WGTP", "TEN", "BLD", "HINCP", "ADJINC"),
    "housing PUMS frame"
  )
  require_columns(person, c("SERIALNO", "RELSHIPP", "AGEP", "SEX"), "person PUMS frame")

  if (anyDuplicated(housing$SERIALNO)) {
    stop("Housing PUMS SERIALNO must be unique for the pipeline's one-to-one join.")
  }

  rows <- list()
  rows[[length(rows) + 1L]] <- funnel_row("raw: all California housing records", housing)

  occupied <- housing[!is.na(as_number(housing$TEN)), , drop = FALSE]
  rows[[length(rows) + 1L]] <- funnel_row("pre-screen: occupied housing units", occupied)

  detached <- occupied[
    !is.na(as_number(occupied$BLD)) & as_number(occupied$BLD) == DETACHED_SINGLE_FAMILY,
    ,
    drop = FALSE
  ]
  rows[[length(rows) + 1L]] <- funnel_row(
    "screen 1: detached single-family house",
    detached,
    "BLD = 02"
  )

  detached$household_income <-
    as_number(detached$HINCP) * as_number(detached$ADJINC) / 1000000
  income_ok <- detached[
    !is.na(detached$household_income) & detached$household_income >= MIN_HOUSEHOLD_INCOME,
    ,
    drop = FALSE
  ]
  rows[[length(rows) + 1L]] <- funnel_row(
    "screen 2: adjusted household income >= $100,000",
    income_ok,
    "HINCP x ADJINC / 1,000,000"
  )

  householders <- person[
    !is.na(as_number(person$RELSHIPP)) & as_number(person$RELSHIPP) == REFERENCE_PERSON,
    c("SERIALNO", "AGEP", "SEX"),
    drop = FALSE
  ]
  if (anyDuplicated(householders$SERIALNO)) {
    stop("Householder SERIALNO must be unique for the pipeline's one-to-one join.")
  }

  joined <- merge(
    income_ok,
    householders,
    by = "SERIALNO",
    all = FALSE,
    sort = FALSE
  )
  rows[[length(rows) + 1L]] <- funnel_row("joined to householder record", joined)

  age <- as_number(joined$AGEP)
  age_ok <- joined[!is.na(age) & age >= MIN_AGE & age <= MAX_AGE, , drop = FALSE]
  rows[[length(rows) + 1L]] <- funnel_row(
    "screen 3: householder aged 30-65",
    age_ok,
    "inclusive"
  )

  weight <- as_number(age_ok$WGTP)
  pool <- age_ok[!is.na(weight) & weight > 0, , drop = FALSE]
  rows[[length(rows) + 1L]] <- funnel_row(
    "eligible pool: positive housing weight",
    pool,
    "WGTP > 0"
  )

  selected <- weighted_draw(pool, draw_n, seed)
  rows[[length(rows) + 1L]] <- data.frame(
    stage = "final weighted draw",
    records = nrow(selected),
    weighted_households = NA_real_,
    detail = sprintf("without replacement; probability proportional to WGTP; seed %d", seed),
    stringsAsFactors = FALSE
  )

  list(funnel = do.call(rbind, rows), selected = selected, pool = pool)
}

screen_persona_draw <- function(personas) {
  require_columns(
    personas,
    c("persona_id", "home_type", "exact_household_income", "exact_age"),
    "personas-B.csv"
  )
  if (nrow(personas) == 0L) {
    stop("personas-B.csv contains no persona rows.")
  }
  ids <- trimws(as.character(personas$persona_id))
  if (any(ids == "") || anyDuplicated(ids)) {
    stop("personas-B.csv persona_id values must be present and unique.")
  }

  detached <- tolower(trimws(as.character(personas$home_type))) == "detached single-family"
  income <- as_number(personas$exact_household_income)
  age <- as_number(personas$exact_age)

  if (any(is.na(detached)) || any(!detached)) {
    stop("The final persona draw contains a row outside the detached single-family screen.")
  }
  if (any(is.na(income)) || any(income < MIN_HOUSEHOLD_INCOME)) {
    stop("The final persona draw contains a row below the $100,000 income screen.")
  }
  if (any(is.na(age)) || any(age < MIN_AGE | age > MAX_AGE)) {
    stop("The final persona draw contains a row outside the inclusive age 30-65 screen.")
  }

  selected_n <- nrow(personas)
  unavailable <- NA_real_
  rows <- data.frame(
    stage = c(
      "raw: all California housing records",
      "pre-screen: occupied housing units",
      "screen 1: detached single-family house",
      "screen 2: adjusted household income >= $100,000",
      "joined to householder record",
      "screen 3: householder aged 30-65",
      "eligible pool: positive housing weight",
      "final weighted draw"
    ),
    records = c(rep(unavailable, 7L), selected_n),
    weighted_households = rep(unavailable, 8L),
    detail = c(
      "unavailable: source PUMS housing frame is not in personas-B.csv",
      "unavailable: TEN is not in personas-B.csv",
      sprintf("pool N unavailable; %d/%d selected rows have the detached label", selected_n, selected_n),
      sprintf(
        "pool N unavailable; %d/%d selected rows have adjusted income >= $100,000; HINCP and ADJINC are absent",
        selected_n,
        selected_n
      ),
      "unavailable: source person frame and RELSHIPP are not in personas-B.csv",
      sprintf("pool N unavailable; %d/%d selected rows have exact age 30-65", selected_n, selected_n),
      "unavailable: WGTP is not in personas-B.csv",
      sprintf(
        "%d selected personas; WGTP and source Census IDs are absent, so weighted selection cannot be rechecked",
        selected_n
      )
    ),
    stringsAsFactors = FALSE
  )

  list(funnel = rows, selected = personas)
}

read_parquet_frame <- function(path) {
  if (!requireNamespace("arrow", quietly = TRUE)) {
    stop(
      "Reading PUMS parquet inputs requires the R package 'arrow'. ",
      "Install it or pass --personas path/to/personas-B.csv for the documented fallback."
    )
  }
  as.data.frame(arrow::read_parquet(path))
}

format_count <- function(value) {
  ifelse(is.na(value), "unavailable", format(value, big.mark = ",", scientific = FALSE, trim = TRUE))
}

print_report <- function(result, source, mode) {
  cat("Neo Smart Living PUMS screen counts\n")
  cat("Source:", source, "\n")
  cat("Mode:", mode, "\n\n")

  table <- result$funnel
  for (index in seq_len(nrow(table))) {
    cat(sprintf(
      "%-55s records: %-12s weighted households: %s\n",
      table$stage[index],
      format_count(table$records[index]),
      format_count(table$weighted_households[index])
    ))
    if (nzchar(table$detail[index])) {
      cat("  ", table$detail[index], "\n", sep = "")
    }
  }

  if (identical(mode, "persona CSV fallback")) {
    cat(
      "\nMissing from this branch: the raw housing/person PUMS frames and their funnel counts, ",
      "the original HINCP and ADJINC fields, WGTP weights, and source Census IDs. ",
      "Only final-draw N and selected-row screen compliance are derivable.\n",
      sep = ""
    )
  }
}

script_repo_root <- function() {
  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg) == 0L) {
    return(normalizePath(".", mustWork = TRUE))
  }
  script <- normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)
  dirname(dirname(script))
}

parse_cli <- function(args) {
  options <- list(housing = NULL, person = NULL, personas = NULL, draw_n = DEFAULT_DRAW_N, seed = DEFAULT_SEED)
  if ("--help" %in% args) {
    cat(
      "Usage: Rscript analysis/screen_counts.R [--housing FILE --person FILE] ",
      "[--personas FILE] [--draw-n N] [--seed N]\n"
    )
    quit(status = 0L)
  }

  index <- 1L
  while (index <= length(args)) {
    key <- args[[index]]
    if (!key %in% c("--housing", "--person", "--personas", "--draw-n", "--seed")) {
      stop(sprintf("Unknown argument: %s", key))
    }
    if (index == length(args)) {
      stop(sprintf("Missing value after %s", key))
    }
    value <- args[[index + 1L]]
    name <- switch(
      key,
      "--housing" = "housing",
      "--person" = "person",
      "--personas" = "personas",
      "--draw-n" = "draw_n",
      "--seed" = "seed"
    )
    options[[name]] <- if (name %in% c("draw_n", "seed")) as.integer(value) else value
    index <- index + 2L
  }
  options
}

first_existing <- function(paths) {
  paths <- paths[!is.na(paths) & nzchar(paths)]
  existing <- paths[file.exists(paths)]
  if (length(existing) == 0L) NULL else normalizePath(existing[[1L]], mustWork = TRUE)
}

main <- function(args = commandArgs(trailingOnly = TRUE)) {
  options <- parse_cli(args)
  root <- script_repo_root()
  default_housing <- file.path(root, "research", "neo_persona_set", "out", "acs_housing_slim.parquet")
  default_person <- file.path(root, "research", "neo_persona_set", "out", "acs_person_slim.parquet")
  housing_path <- options$housing %||% default_housing
  person_path <- options$person %||% default_person

  explicit_pums <- !is.null(options$housing) || !is.null(options$person)
  missing_pums <- c(
    if (!file.exists(housing_path)) sprintf("housing: %s", housing_path),
    if (!file.exists(person_path)) sprintf("person: %s", person_path)
  )
  if (explicit_pums && length(missing_pums) > 0L) {
    stop(
      "Explicit PUMS input was not found (", paste(missing_pums, collapse = "; "), "). ",
      "Refusing to silently use the persona CSV fallback."
    )
  }

  if (file.exists(housing_path) && file.exists(person_path)) {
    housing <- read_parquet_frame(housing_path)
    person <- read_parquet_frame(person_path)
    result <- screen_pums_frames(housing, person, options$draw_n, options$seed)
    print_report(
      result,
      sprintf("%s + %s", normalizePath(housing_path), normalizePath(person_path)),
      "PUMS frame"
    )
    return(invisible(result))
  }

  persona_path <- first_existing(c(
    options$personas,
    Sys.getenv("NEO_PERSONA_CSV", unset = ""),
    Sys.getenv("DEMO_PERSONA_CSV", unset = ""),
    file.path(root, "personas-B.csv"),
    path.expand("~/dev/aytm-real-data/personas/personas-B.csv")
  ))
  if (is.null(persona_path)) {
    stop(
      "PUMS parquet inputs are absent and personas-B.csv was not found. ",
      "Pass --housing and --person, or --personas path/to/personas-B.csv."
    )
  }

  personas <- utils::read.csv(persona_path, check.names = FALSE, stringsAsFactors = FALSE)
  result <- screen_persona_draw(personas)
  print_report(result, persona_path, "persona CSV fallback")
  invisible(result)
}

`%||%` <- function(left, right) {
  if (is.null(left)) right else left
}

if (sys.nframe() == 0L) {
  main()
}
