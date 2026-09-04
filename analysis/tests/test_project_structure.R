analysis_root <- file.path(repo_root, "analysis")

required_directories <- c("R", "data", "output", "tests")
for (directory in required_directories) {
  stopifnot(dir.exists(file.path(analysis_root, directory)))
}

r_project_path <- file.path(analysis_root, "SyntheticResponderLab-analysis.Rproj")
stopifnot(file.exists(r_project_path))
r_project <- readLines(r_project_path, warn = FALSE)
stopifnot(
  "Version: 1.0" %in% r_project,
  "RestoreWorkspace: No" %in% r_project,
  "SaveWorkspace: No" %in% r_project,
  "Encoding: UTF-8" %in% r_project
)

lockfile_path <- file.path(analysis_root, "renv.lock")
stopifnot(file.exists(lockfile_path))
lockfile <- paste(readLines(lockfile_path, warn = FALSE), collapse = "\n")
expected_r_version <- paste(R.version$major, R.version$minor, sep = ".")
stopifnot(
  grepl(sprintf('"Version": "%s"', expected_r_version), lockfile, fixed = TRUE),
  grepl('"Name": "CRAN"', lockfile, fixed = TRUE),
  grepl('"Package": "renv"', lockfile, fixed = TRUE)
)

cat("test_project_structure.R: PASS\n")
