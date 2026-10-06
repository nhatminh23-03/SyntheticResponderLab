import test from "node:test";
import assert from "node:assert/strict";

import { JEV_MODEL_ID, normalizeSelectedModels, selectedModelsProblem, toggleModel } from "../src/lib/experiment-models";
import { DEFAULT_LIKERT_ANCHORS, isStudentQuestion, toAddQuestionPayload, validateAddedQuestion } from "../src/lib/survey-question-form";
import { demoBannerLines, describeDemoRun, isDemoGenerationMode, runErrorNote } from "../src/lib/demo-run";
import { liveEngineAvailable, toBackendReadinessPayload } from "../src/lib/backend-readiness";

test("Jev and other models are mutually exclusive", () => {
  assert.deepEqual(toggleModel(["openai/gpt-4o-mini"], JEV_MODEL_ID), [JEV_MODEL_ID]);
  assert.deepEqual(toggleModel([JEV_MODEL_ID], "openai/gpt-4o-mini"), ["openai/gpt-4o-mini"]);
  assert.deepEqual(toggleModel([JEV_MODEL_ID], JEV_MODEL_ID), []);
});

test("Jev alone survives normalization; otherwise two models are required", () => {
  assert.deepEqual(normalizeSelectedModels([JEV_MODEL_ID], ["a", "b"], true), [JEV_MODEL_ID]);
  assert.deepEqual(normalizeSelectedModels([], ["a", "b"], true), [JEV_MODEL_ID]);
  assert.deepEqual(normalizeSelectedModels([], ["a", "b"], false), ["a", "b"]);
  assert.deepEqual(normalizeSelectedModels(["x", JEV_MODEL_ID, "y"], ["a", "b"], true), ["x", "y"]);
});

test("added-question validation matches the API rules", () => {
  assert.equal(validateAddedQuestion({ text: "Rate the solar roof", questionType: "likert", options: [...DEFAULT_LIKERT_ANCHORS] }), null);
  assert.match(validateAddedQuestion({ text: "Hi", questionType: "likert", options: [...DEFAULT_LIKERT_ANCHORS] }) ?? "", /5 characters/);
  assert.match(validateAddedQuestion({ text: "Pick a colour", questionType: "single_choice", options: ["Oak"] }) ?? "", /2 to 8/);
  assert.deepEqual(toAddQuestionPayload({ text: " Pick  a colour ", questionType: "single_choice", options: [" Oak", "Slate ", ""] }),
    { text: "Pick a colour", question_type: "single_choice", options: ["Oak", "Slate"] });
  assert.equal(isStudentQuestion("SQ3"), true);
  assert.equal(isStudentQuestion("Q1"), false);
});

test("demo runs are described, live runs are not", () => {
  assert.equal(describeDemoRun({ generation_mode: "jev_live", warnings: [] }), null);
  const demo = describeDemoRun({ generation_mode: "demo_preloaded", warnings: ["Preloaded demo: ...", "No AI key is configured ..."], demo: { reason: "no_key" } });
  assert.equal(demo?.reason, "no_key");
  assert.match(demo?.message ?? "", /No AI key/);
});

test("readiness passes providers through", () => {
  const ready = toBackendReadinessPayload(200, { data: { status: "degraded", providers: { jev: true, openrouter: false } } });
  assert.deepEqual(ready.providers, { jev: true, openrouter: false });
  assert.equal(liveEngineAvailable(ready), true);
  assert.equal(liveEngineAvailable(toBackendReadinessPayload(200, { data: { status: "ok" } })), false);
});

test("Jev is not kept when the server has no Jev key", () => {
  assert.deepEqual(normalizeSelectedModels([JEV_MODEL_ID], ["a", "b"], false), ["a", "b"]);
  assert.deepEqual(normalizeSelectedModels([JEV_MODEL_ID], ["a", "b"], true), [JEV_MODEL_ID]);
});

test("a lone Jev passes the client model rule in split and mirror, but not stability", () => {
  assert.equal(selectedModelsProblem([JEV_MODEL_ID], "split"), null);
  assert.equal(selectedModelsProblem([JEV_MODEL_ID], "mirror"), null);
  assert.match(selectedModelsProblem([JEV_MODEL_ID], "stability") ?? "", /split or mirror/);
  assert.equal(selectedModelsProblem(["a"], "split"), "Select at least 2 models.");
  assert.equal(selectedModelsProblem([], "mirror"), "Select at least 2 models.");
  assert.equal(selectedModelsProblem(["a", "b"], "split"), null);
});

test("the demo banner lists the message and every remaining warning on its own line", () => {
  const lines = demoBannerLines({
    generation_mode: "demo_preloaded",
    warnings: ["Preloaded demo: x.", "You chose the preloaded demo.", "Detail: boom", "Run live to answer these: SQ1"],
    demo: { reason: "requested" },
  });
  assert.deepEqual(lines, ["Preloaded demo: x. You chose the preloaded demo.", "Detail: boom", "Run live to answer these: SQ1"]);
  assert.deepEqual(demoBannerLines({ generation_mode: "jev_live", warnings: ["a", "b", "c"] }), []);
  assert.deepEqual(demoBannerLines(null), []);
});

test("only a message that needs a live run gets the added-questions note", () => {
  assert.equal(
    runErrorNote("Jev is temporarily unavailable. Your new question requires a live run. You can view the preloaded demo of the original survey."),
    "Your added questions are not in the preloaded demo."
  );
  assert.equal(runErrorNote("Jev answered only 70 of 100 respondents."), null);
  assert.equal(runErrorNote("The preloaded demo covers the Tahoe Mini survey; use a live run for this survey."), null);
});

test("a run is a preloaded demo only when its generation_mode says so", () => {
  assert.equal(isDemoGenerationMode("demo_preloaded"), true);
  for (const mode of ["jev_live", "openrouter_live", "mock", "", null, undefined]) {
    assert.equal(isDemoGenerationMode(mode), false);
  }
});
