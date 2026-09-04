args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) == 0L) {
  stop("test_all.R must be run with Rscript")
}

test_file <- normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE)
repo_root <- dirname(dirname(dirname(test_file)))
tests_dir <- dirname(test_file)

test_files <- sort(list.files(
  tests_dir,
  pattern = "^test_.*\\.R$",
  full.names = TRUE
))
test_files <- test_files[basename(test_files) != basename(test_file)]

if (length(test_files) == 0L) {
  stop("The analysis R suite did not discover any test files.")
}

for (path in test_files) {
  cat(sprintf("[analysis:test] %s\n", basename(path)))
  test_environment <- new.env(parent = globalenv())
  test_environment$repo_root <- repo_root
  sys.source(path, envir = test_environment)
}

cat(sprintf("analysis R suite: PASS (%d files)\n", length(test_files)))
