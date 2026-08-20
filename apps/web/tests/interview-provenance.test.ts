import test from "node:test";
import assert from "node:assert/strict";

import { describeInterviewProvenance } from "../src/lib/interview-provenance";

test("flags a Neo fixture run as seeded rather than a live interview batch", () => {
  const provenance = describeInterviewProvenance({
    demo_fixture: true,
    fixture_source: "generated_fallback",
    judge_model: "demo/stamp-fixture",
    model_a: "openai/gpt-4.1-mini",
    model_b: "google/gemini-2.5-flash",
  });

  assert.equal(provenance.isFixture, true);
  assert.match(provenance.headline, /seeded|demo/i);
});

test("does not credit a fixture run with dual-model verification or a judge LLM", () => {
  const provenance = describeInterviewProvenance({
    demo_fixture: true,
    fixture_source: "generated_fallback",
    judge_model: "demo/stamp-fixture",
    model_a: "openai/gpt-4.1-mini",
    model_b: "google/gemini-2.5-flash",
  });

  assert.equal(provenance.claimsDualModel, false);
  assert.equal(provenance.claimsJudgeModel, false);
  assert.match(provenance.detail, /no .*model|not .*generated|placeholder/i);
});

test("describes a live run as genuinely dual-model and names its real judge", () => {
  const provenance = describeInterviewProvenance({
    demo_fixture: false,
    fixture_source: null,
    judge_model: "openai/o4-mini",
    model_a: "openai/gpt-4o-mini",
    model_b: "google/gemini-2.5-flash",
  });

  assert.equal(provenance.isFixture, false);
  assert.equal(provenance.claimsDualModel, true);
  assert.equal(provenance.claimsJudgeModel, true);
  assert.match(provenance.detail, /openai\/o4-mini/);
});

test("treats an absent run as not yet verifiable rather than assuming it is live", () => {
  const provenance = describeInterviewProvenance(null);

  assert.equal(provenance.isFixture, false);
  assert.equal(provenance.claimsDualModel, false);
  assert.equal(provenance.claimsJudgeModel, false);
});

test("qualifies the grounding score for a fixture run so 100% is not read as model agreement", () => {
  const provenance = describeInterviewProvenance({
    demo_fixture: true,
    fixture_source: "generated_fallback",
    judge_model: "demo/stamp-fixture",
  });

  assert.notEqual(provenance.groundingScoreCaveat, null);
  assert.match(String(provenance.groundingScoreCaveat), /fit tier|not .*agreement/i);
});

test("leaves the grounding score unqualified for a genuine judged run", () => {
  const provenance = describeInterviewProvenance({
    demo_fixture: false,
    judge_model: "openai/o4-mini",
  });

  assert.equal(provenance.groundingScoreCaveat, null);
});
