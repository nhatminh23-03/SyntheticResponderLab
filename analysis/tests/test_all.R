args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) == 0L) {
  stop("test_all.R must be run with Rscript")
}

test_file <- normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)
repo_root <- dirname(dirname(dirname(test_file)))

source(file.path(repo_root, "analysis", "tests", "test_screen_counts.R"), local = TRUE)
cat("analysis R suite: PASS\n")
