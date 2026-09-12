# Invented data only: this fixture contains no source survey rows or headers.
arm_c_fixture <- function() {
  ids <- c("Age", "Gender", "Income", "PQ1", "Race", "Employment", sprintf("Q%d", 1:36))
  student <- data.frame(row.names = seq_len(256L))
  aytm <- data.frame(row.names = seq_len(600L))
  synthetic <- data.frame(synthetic_id = sprintf("arm_c_%03d", seq_len(256L)))
  for (index in seq_along(ids)) {
    id <- ids[[index]]
    left <- switch(id,
      Age = ARM_B_AGE_LEVELS,
      Gender = c("Female", "Male"),
      Income = c("Under $50,000", "$50,000-$74,999", "$75,000-$99,999",
        "$100,000-$149,999", "$150,000-$199,999", "$200,000+"),
      PQ1 = c("Yes", "No", "Possibly"),
      Race = c("White", "Asian"),
      Employment = c("Full time employed", "Retired"),
      as.character(1:5)
    )
    right <- switch(id,
      Age = c("22", "30", "40", "50", "60", "70"),
      Income = c("Under $25,000", "$25,000-$49,999", "$50,000-$74,999",
        "$75,000-$99,999", "$100,000-$199,999", "$200,000+"),
      PQ1 = c("Yes", "Possibly"),
      if (startsWith(id, "Q")) paste0(1:5, " - Example anchor") else left
    )
    student[[paste0("aytm:", id, " | invented student label")]] <- rep(left, length.out = 256L)
    aytm[[paste0(id, ": invented panel label")]] <- rep(right, length.out = 600L)
    synthetic[[id]] <- rep(switch(id,
      Race = c("white", "other / multiracial"),
      Employment = c("employed", "not employed / other"),
      PQ1 = c("yes", "possibly"),
      as.character(c(2, 4, 1, 5, 3))
    ), length.out = 256L)
  }
  mapping <- data.frame(match_status = "Matched", aytm_column = names(aytm),
    student_column = c(names(student)[1:23], paste0("abbreviated_", 24:42)),
    notes = c(rep("Compare distributions", 6L), rep("1-5 compare means", 36L)))
  registry <- data.frame(question_id = ids,
    question_type = c(rep("categorical", 6L), rep("continuous", 36L)),
    equivalence_margin = c(rep(0.2, 6L), rep(0.5, 36L)))
  donors <- expand.grid(age = c(22, 30, 40, 50, 60, 70),
    income = c(10000, 60000, 85000, 120000, 220000), sex = 1:2,
    replicate = seq_len(12L), KEEP.OUT.ATTRS = FALSE)
  housing <- data.frame(SERIALNO = sprintf("C%04d", seq_len(nrow(donors))),
    ST = 6, WGTP = 1 + seq_len(nrow(donors)) %% 13L, TEN = 1,
    HINCP = donors$income, ADJINC = 1000000)
  person <- data.frame(SERIALNO = housing$SERIALNO, ST = 6, RELSHIPP = 20,
    AGEP = donors$age, SEX = donors$sex)
  list(housing = housing, person = person, student_data = student, aytm_data = aytm,
    mapping = mapping, synthetic_data = synthetic, registry = registry)
}
