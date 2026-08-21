import test from "node:test";
import assert from "node:assert/strict";

import { formatAnswerSourcing } from "../src/lib/answer-sourcing";

test("states how many answers were used and how many were excluded", () => {
  const s = formatAnswerSourcing({
    live_answers_used: 122,
    fallback_answers_excluded: 6,
    total_answers: 128,
    live_answer_rate: 0.953,
  });

  assert.equal(s.shown, true);
  assert.equal(s.liveAnswers, 122);
  assert.equal(s.excluded, 6);
  assert.equal(s.ratePercent, 95.3);
  assert.match(s.summary, /122/);
  assert.match(s.summary, /6/);
});

test("says so plainly when nothing was excluded", () => {
  const s = formatAnswerSourcing({
    live_answers_used: 30,
    fallback_answers_excluded: 0,
    total_answers: 30,
    live_answer_rate: 1,
  });

  assert.equal(s.excluded, 0);
  assert.equal(s.ratePercent, 100);
  assert.match(s.summary, /all/i);
});

test("claims nothing when the run reported no sourcing", () => {
  const s = formatAnswerSourcing(null);
  assert.equal(s.shown, false);
});

test("a run with no live answers says so instead of reporting what it was built from", () => {
  // F-17. "Built from 0 live answers" describes a construction that did not happen; the run produced
  // nothing to build from, and the reader needs to be told that rather than shown a zero.
  const sourcing = formatAnswerSourcing({
    live_answers_used: 0,
    fallback_answers_excluded: 128,
    total_answers: 128,
    live_answer_rate: 0,
  });

  assert.equal(sourcing.shown, true);
  assert.equal(sourcing.liveAnswers, 0);
  assert.equal(sourcing.excluded, 128);
  assert.equal(sourcing.ratePercent, 0);
  assert.ok(
    !sourcing.summary.startsWith("Built from"),
    `nothing was built from these answers: ${sourcing.summary}`
  );
  assert.match(sourcing.summary, /No live model answers/);
  assert.match(sourcing.summary, /remain in the saved records/);
});
