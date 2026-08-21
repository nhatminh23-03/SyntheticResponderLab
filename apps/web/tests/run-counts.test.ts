import test from "node:test";
import assert from "node:assert/strict";

import { describeRunCounts } from "../src/lib/run-counts";

/**
 * F-05. A mirror run of N personas across M models performs N x M surveys and stores
 * N x M x questions rows. The Result tile counted distinct respondent ids, which mirror mode
 * deliberately reuses across models, so it showed N for a run that produced N x M.
 */

const MIRROR_RECORDS = [
  { respondent_id: "RESP_001", model: "a" },
  { respondent_id: "RESP_001", model: "b" },
  { respondent_id: "RESP_002", model: "a" },
  { respondent_id: "RESP_002", model: "b" },
];

test("a mirror run reports executions, not personas, as its response count", () => {
  const counts = describeRunCounts({
    run_counts: { personas: 2, executions: 4, questions: 32, answer_records: 128 },
  });

  assert.equal(counts.personas, 2);
  assert.equal(counts.executions, 4);
  assert.equal(counts.answerRecords, 128);
  assert.equal(counts.responsesLabel, "Responses");
  assert.equal(counts.responsesValue, "4");
});

test("the detail line names each quantity so none of them can be mistaken for another", () => {
  const counts = describeRunCounts({
    run_counts: { personas: 20, executions: 40, questions: 32, answer_records: 1280 },
  });

  assert.equal(counts.detail, "20 personas · 40 completed surveys · 1,280 answers");
});

test("a split run, where each persona answers once, reads the same either way", () => {
  const counts = describeRunCounts({
    run_counts: { personas: 4, executions: 4, questions: 3, answer_records: 12 },
  });

  assert.equal(counts.responsesValue, "4");
  assert.equal(counts.detail, "4 personas · 4 completed surveys · 12 answers");
});

test("a run saved before run_counts existed is derived from its records, not shown as zero", () => {
  const counts = describeRunCounts({
    response_records: MIRROR_RECORDS,
    question_count: 2,
  });

  assert.equal(counts.personas, 2, "distinct respondent ids");
  assert.equal(counts.executions, 4, "distinct respondent-model pairs");
  assert.equal(counts.answerRecords, 4, "the rows actually present");
  assert.equal(counts.responsesValue, "4");
});

test("a run with nothing to count says so rather than reporting zero as a result", () => {
  const counts = describeRunCounts(null);

  assert.equal(counts.available, false);
  assert.equal(counts.responsesValue, "—");
  assert.equal(counts.detail, "No run has been saved yet.");
});

test("the preview record set is used when the full set was not stored", () => {
  const counts = describeRunCounts({
    response_record_preview: MIRROR_RECORDS,
    question_count: 2,
  });

  assert.equal(counts.executions, 4);
  assert.equal(counts.isPartial, true, "a preview is a sample, and must not read as the whole run");
});
