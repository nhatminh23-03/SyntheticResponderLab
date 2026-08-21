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
