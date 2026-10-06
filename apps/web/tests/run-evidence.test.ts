import test from "node:test";
import assert from "node:assert/strict";

import { describeRunEvidence } from "../src/lib/run-evidence";

const LIVE = {
  total_answers: 18,
  truly_live_answers: 18,
  fallback_answers: 0,
  provider_error_count: 0,
  malformed_json_count: 0,
  live_answer_rate: 1,
};

test("a fully live run reads as trustworthy and reports 100%", () => {
  const evidence = describeRunEvidence(LIVE, "grounded_priors");

  assert.equal(evidence.available, true);
  assert.equal(evidence.tone, "ok");
  assert.equal(evidence.liveAnswerRatePercent, 100);
  assert.equal(evidence.fabricatedAnswers, 0);
});

test("a partly fabricated run surfaces the fabricated count instead of hiding it", () => {
  const evidence = describeRunEvidence(
    { ...LIVE, truly_live_answers: 189, total_answers: 192, fallback_answers: 3, live_answer_rate: 0.984 },
    "heuristic_only"
  );

  assert.equal(evidence.tone, "caution");
  assert.equal(evidence.fabricatedAnswers, 3);
  assert.equal(evidence.liveAnswerRatePercent, 98.4);
  assert.match(evidence.detail, /3\b/);
});

test("a run with no live answers is critical, not merely cautionary", () => {
  const evidence = describeRunEvidence(
    { ...LIVE, truly_live_answers: 0, fallback_answers: 18, live_answer_rate: 0, provider_error_count: 6 },
    "heuristic_only"
  );

  assert.equal(evidence.tone, "critical");
  assert.equal(evidence.liveAnswerRatePercent, 0);
  assert.match(evidence.headline, /no live|not live|fabricat/i);
});

test("provider errors and malformed responses are reported separately", () => {
  const evidence = describeRunEvidence(
    { ...LIVE, provider_error_count: 4, malformed_json_count: 2 },
    "heuristic_only"
  );

  assert.equal(evidence.providerErrors, 4);
  assert.equal(evidence.malformedJson, 2);
});

test("an absent summary claims nothing rather than implying a clean run", () => {
  const evidence = describeRunEvidence(null, null);

  assert.equal(evidence.available, false);
  assert.equal(evidence.liveAnswerRatePercent, null);
  assert.notEqual(evidence.tone, "ok");
});

test("heuristic persona generation is not described as grounded", () => {
  const evidence = describeRunEvidence(LIVE, "heuristic_only");

  assert.equal(evidence.personaGrounding.isGrounded, false);
  assert.match(evidence.personaGrounding.label, /rule-based|heuristic|not grounded/i);
});

test("genuinely grounded persona generation is reported as grounded", () => {
  const evidence = describeRunEvidence(LIVE, "grounded_priors");

  assert.equal(evidence.personaGrounding.isGrounded, true);
  assert.match(evidence.personaGrounding.label, /grounded/i);
});

test("a preloaded demo is a preloaded panel, not a failed grounding", () => {
  const evidence = describeRunEvidence({}, "preloaded_s1", "demo_preloaded");

  assert.equal(evidence.personaGrounding.isGrounded, false);
  assert.equal(evidence.personaGrounding.label, "Preloaded panel (100 synthetic personas, S1)");
  assert.doesNotMatch(evidence.personaGrounding.detail, /unavailable|heuristic/i);
});

test("a preloaded demo never reads as live answers or an empty live run", () => {
  const evidence = describeRunEvidence({}, "preloaded_s1", "demo_preloaded");

  assert.equal(evidence.available, false);
  assert.equal(evidence.headline, "Preloaded demo answers");
  assert.doesNotMatch(`${evidence.headline} ${evidence.detail}`, /live model|not reported|fabricat/i);
  assert.match(evidence.detail, /No AI was called/);
});
