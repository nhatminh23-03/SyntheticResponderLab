import test from "node:test";
import assert from "node:assert/strict";

import {
  REQUIRED_SELECTION_COUNT,
  buildCandidateCsv,
  canFinalize,
  candidateCountText,
  selectionCounterText,
  setReviewerNote,
  toggleSelection,
} from "../src/lib/persona-selection";

/**
 * Dr. Wang's review flow: 15 grounded candidates, exactly 5 selected, selection and notes
 * exported as CSV. The pure helpers here enforce the exactly-5 rule and keep the CSV to a
 * whitelisted column set so no internal prompts or unexpected persona keys can leak.
 */

const CANDIDATES = ["c-1", "c-2", "c-3", "c-4", "c-5", "c-6"];

test("toggleSelection adds an unselected candidate and removes a selected one", () => {
  const afterAdd = toggleSelection([], "c-1");
  assert.deepEqual(afterAdd, ["c-1"]);

  const afterRemove = toggleSelection(["c-1", "c-2"], "c-1");
  assert.deepEqual(afterRemove, ["c-2"]);
});

test("toggleSelection blocks a sixth selection", () => {
  const five = CANDIDATES.slice(0, 5);
  const result = toggleSelection(five, "c-6");
  assert.deepEqual(result, five);
});

test("canFinalize is true only at exactly five selections", () => {
  assert.equal(REQUIRED_SELECTION_COUNT, 5);
  assert.equal(canFinalize(CANDIDATES.slice(0, 4)), false);
  assert.equal(canFinalize(CANDIDATES.slice(0, 5)), true);
  assert.equal(canFinalize(CANDIDATES.slice(0, 6)), false);
  assert.equal(canFinalize([]), false);
});

test("counter and candidate-count copy match the review page contract", () => {
  assert.equal(selectionCounterText(0), "Selected 0 / 5");
  assert.equal(selectionCounterText(5), "Selected 5 / 5");
  assert.equal(candidateCountText(15), "15 candidates generated");
});

test("setReviewerNote stores trimmed notes and clears empty ones", () => {
  const withNote = setReviewerNote({}, "c-1", "  strong anchor  ");
  assert.deepEqual(withNote, { "c-1": "strong anchor" });

  const cleared = setReviewerNote(withNote, "c-1", "   ");
  assert.deepEqual(cleared, {});
});

const PERSONA = {
  candidate_id: "c-1",
  persona_id: "PERS_001",
  segment_label: "Backyard office homeowners",
  fit_tier: "strong",
  age_bucket: "35-44",
  income_bucket: "middle",
  ownership: "own",
  home_type: "single_family",
  household_size_bucket: "3-4",
  work_mode: "remote",
  likely_use_case: "backyard office",
  likely_barrier: "permit uncertainty",
  awareness_stage: "aware",
  internal_prompt: "MUST NOT LEAK",
  row_index: 0,
};

const EXPECTED_HEADER =
  "persona_id,segment_label,fit_tier,age_bucket,income_bucket,ownership,home_type," +
  "household_size_bucket,work_mode,likely_use_case,likely_barrier,awareness_stage," +
  "generation_mode,review_status,reviewer_notes";

test("buildCandidateCsv emits exactly the whitelisted columns", () => {
  const csv = buildCandidateCsv({
    candidates: [PERSONA],
    selectedIds: ["c-1"],
    reviewerNotes: {},
    generationMode: "grounded_priors",
  });

  const [header, row] = csv.split("\r\n");
  assert.equal(header, EXPECTED_HEADER);
  assert.equal(
    row,
    "PERS_001,Backyard office homeowners,strong,35-44,middle,own,single_family," +
      "3-4,remote,backyard office,permit uncertainty,aware,grounded_priors,selected,"
  );
  assert.ok(!csv.includes("MUST NOT LEAK"));
  assert.ok(!csv.includes("row_index"));
});

test("buildCandidateCsv marks unselected candidates and escapes notes RFC-4180 style", () => {
  const csv = buildCandidateCsv({
    candidates: [PERSONA, { ...PERSONA, candidate_id: "c-2", persona_id: "PERS_002" }],
    selectedIds: ["c-2"],
    reviewerNotes: { "c-2": 'tricky, "quoted"\nnote' },
    generationMode: "grounded_priors",
  });

  const rows = csv.split("\r\n");
  assert.equal(rows.length, 3);
  assert.ok(rows[1].endsWith("not_selected,"));
  assert.ok(rows[2].includes('"tricky, ""quoted""\nnote"'));
});

test("buildCandidateCsv writes empty cells for missing persona fields", () => {
  const csv = buildCandidateCsv({
    candidates: [{ candidate_id: "c-9", persona_id: "PERS_009" }],
    selectedIds: [],
    reviewerNotes: {},
    generationMode: null,
  });

  const [, row] = csv.split("\r\n");
  assert.equal(row, "PERS_009,,,,,,,,,,,,,not_selected,");
});
