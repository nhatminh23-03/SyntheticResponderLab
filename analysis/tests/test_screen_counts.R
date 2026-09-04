screen_counts_path <- file.path(repo_root, "analysis", "screen_counts.R")
source(screen_counts_path, local = TRUE)

assert_error <- function(expression, pattern) {
  message <- tryCatch(
    {
      force(expression)
      NULL
    },
    error = function(error) conditionMessage(error)
  )
  stopifnot(!is.null(message), grepl(pattern, message, fixed = TRUE))
}

housing <- data.frame(
  SERIALNO = paste0("h", 1:10),
  WGTP = c(1, 2, 3, 1, 2, 3, 4, 5, 0, 6),
  TEN = c(NA, rep(1, 9)),
  BLD = c("02", "03", rep("02", 8)),
  HINCP = c(200000, 200000, 99999, 90000, 100000, 150000, 200000, 120000, 130000, 140000),
  ADJINC = c(rep(1000000, 3), 1200000, rep(1000000, 6)),
  stringsAsFactors = FALSE
)

person <- data.frame(
  SERIALNO = c("h1", "h2", "h3", "h4", "h4", "h5", "h6", "h7", "h8", "h9", "h10"),
  RELSHIPP = c(rep(20, 4), 21, rep(20, 3), 21, 20, 20),
  AGEP = c(40, 40, 40, 30, 8, 65, 29, 66, 45, 45, 45),
  stringsAsFactors = FALSE
)

result <- screen_pums_frames(housing, person, draw_n = 2, seed = 17)
expected_records <- as.integer(c(10, 9, 8, 7, 6, 4, 3, 2))
stopifnot(identical(as.integer(result$funnel$records), expected_records))
stopifnot(result$pool$household_income[result$pool$SERIALNO == "h4"] == 108000)
stopifnot(setequal(result$pool$SERIALNO, c("h4", "h5", "h10")))
stopifnot(all(result$pool$AGEP >= 30 & result$pool$AGEP <= 65))
stopifnot(all(result$pool$WGTP > 0))
stopifnot(nrow(result$selected) == 2L, !anyDuplicated(result$selected$SERIALNO))
stopifnot(is.na(tail(result$funnel$weighted_households, 1L)))

draw_one <- weighted_draw(result$pool, n = 2, seed = 91)
draw_two <- weighted_draw(result$pool, n = 2, seed = 91)
stopifnot(identical(draw_one$SERIALNO, draw_two$SERIALNO))
assert_error(weighted_draw(result$pool, n = 4, seed = 1), "Eligible pool holds only")
bad_weight <- result$pool
bad_weight$WGTP[[1L]] <- 0
assert_error(weighted_draw(bad_weight, n = 2, seed = 1), "finite, positive WGTP")

duplicate_housing <- rbind(housing, housing[1L, , drop = FALSE])
assert_error(
  screen_pums_frames(duplicate_housing, person, draw_n = 2),
  "Housing PUMS SERIALNO must be unique"
)
assert_error(
  screen_pums_frames(housing[, setdiff(names(housing), "ADJINC")], person, draw_n = 2),
  "ADJINC"
)

personas <- data.frame(
  persona_id = c("P001", "P002", "P003"),
  home_type = rep("detached single-family", 3),
  exact_household_income = c(100000, 150000, 225000),
  exact_age = c(30, 65, 44),
  stringsAsFactors = FALSE
)
fallback <- screen_persona_draw(personas)
stopifnot(is.na(fallback$funnel$records[[1L]]))
stopifnot(tail(fallback$funnel$records, 1L) == 3L)
stopifnot(all(is.na(fallback$funnel$weighted_households)))
stopifnot(grepl("3/3 selected rows", fallback$funnel$detail[[3L]], fixed = TRUE))
stopifnot(grepl("HINCP and ADJINC are absent", fallback$funnel$detail[[4L]], fixed = TRUE))
stopifnot(grepl("WGTP", tail(fallback$funnel$detail, 1L), fixed = TRUE))

bad_personas <- personas
bad_personas$exact_age[[1L]] <- 29
assert_error(screen_persona_draw(bad_personas), "outside the inclusive age 30-65 screen")
bad_personas <- personas
bad_personas$exact_household_income[[1L]] <- 99999
assert_error(screen_persona_draw(bad_personas), "below the $100,000 income screen")
bad_personas <- personas
bad_personas$home_type[[1L]] <- "attached"
assert_error(screen_persona_draw(bad_personas), "outside the detached single-family screen")
bad_personas <- personas
bad_personas$persona_id[[2L]] <- "P001"
assert_error(screen_persona_draw(bad_personas), "persona_id values must be present and unique")
assert_error(screen_persona_draw(personas[, -1L]), "persona_id")

fallback_path <- tempfile(fileext = ".csv")
utils::write.csv(personas, fallback_path, row.names = FALSE)
assert_error(
  main(c(
    "--housing", tempfile(fileext = ".parquet"),
    "--person", tempfile(fileext = ".parquet"),
    "--personas", fallback_path
  )),
  "Explicit PUMS input was not found"
)
unlink(fallback_path)

cat("test_screen_counts.R: PASS\n")
