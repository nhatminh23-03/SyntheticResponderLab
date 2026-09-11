import test from "node:test";
import assert from "node:assert/strict";

import {
  canRunInterviewComparison,
  defaultInterviewComparisonModelIds,
  orderInterviewComparisonModelIds,
  POST_INTERVIEW_SCORE_LABEL,
  removeExpensiveComparisonModels,
  runInterviewComparison,
  toggleInterviewComparisonModel,
} from "../src/lib/interview-comparison";
import type { InterviewModelCatalogEntry } from "../src/lib/api";


const cheap: InterviewModelCatalogEntry = {
  id: "provider/cheap",
  name: "Cheap Model",
  tier: "cheap",
  prompt_price_per_million: 0.1,
  completion_price_per_million: 0.4,
  estimated_cost_per_persona_usd: 0.0018,
};

const mid: InterviewModelCatalogEntry = {
  ...cheap,
  id: "provider/mid",
  name: "Mid Model",
  tier: "mid",
};

const expensive: InterviewModelCatalogEntry = {
  ...cheap,
  id: "provider/expensive",
  name: "Expensive Model",
  tier: "expensive",
};


test("comparison defaults to two non-expensive models and requires two unique choices", () => {
  const defaults = defaultInterviewComparisonModelIds([cheap, mid, expensive]);
  assert.deepEqual(defaults, [cheap.id, mid.id]);
  assert.equal(canRunInterviewComparison(defaults), true);
  assert.equal(canRunInterviewComparison([cheap.id, cheap.id]), false);
  assert.equal(canRunInterviewComparison([cheap.id]), false);
});


test("comparison model toggles are idempotent and expensive opt-out removes expensive choices", () => {
  assert.deepEqual(toggleInterviewComparisonModel([cheap.id], mid.id, true), [cheap.id, mid.id]);
  assert.deepEqual(toggleInterviewComparisonModel([cheap.id], cheap.id, true), [cheap.id]);
  assert.deepEqual(toggleInterviewComparisonModel([cheap.id, mid.id], cheap.id, false), [mid.id]);
  assert.deepEqual(
    removeExpensiveComparisonModels([cheap, mid, expensive], [cheap.id, expensive.id]),
    [cheap.id]
  );
  assert.deepEqual(
    orderInterviewComparisonModelIds(
      [cheap, mid, expensive],
      [expensive.id, "provider/not-curated", cheap.id]
    ),
    [cheap.id, expensive.id]
  );
});


test("comparison sends the complete controlled comparison through the budgeted backend", async () => {
  let requestUrl = "";
  let requestBody: Record<string, unknown> = {};
  const results = await runInterviewComparison(
    {
      studyId: "study/unsafe-id",
      personaId: "persona-07",
      question: "What matters most to you?",
      modelIds: [cheap.id, expensive.id],
      allowExpensiveModels: true,
    },
    async (input, init) => {
      requestUrl = input;
      requestBody = JSON.parse(String(init.body)) as Record<string, unknown>;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: {
            interview_comparison: {
              results: [
                {
                  model_id: cheap.id,
                  answer: `Answer from ${cheap.id}`,
                  error: null,
                  post_interview_score: {
                    fit_tier: "soft",
                    emotional_classification: "positive",
                    label: POST_INTERVIEW_SCORE_LABEL,
                  },
                },
                {
                  model_id: expensive.id,
                  answer: `Answer from ${expensive.id}`,
                  error: null,
                  post_interview_score: {
                    fit_tier: "strong",
                    emotional_classification: "neutral",
                    label: POST_INTERVIEW_SCORE_LABEL,
                  },
                },
              ],
            },
          },
        }),
      };
    }
  );

  assert.equal(
    requestUrl,
    "/api/backend/api/v1/studies/study%2Funsafe-id/interview/compare"
  );
  assert.deepEqual(requestBody, {
    persona_id: "persona-07",
    question: "What matters most to you?",
    model_ids: [cheap.id, expensive.id],
    allow_expensive_models: true,
  });
  assert.deepEqual(results, [
    {
      modelId: cheap.id,
      answer: `Answer from ${cheap.id}`,
      error: null,
      postInterviewScore: { fitTier: "soft", emotionalClassification: "positive" },
    },
    {
      modelId: expensive.id,
      answer: `Answer from ${expensive.id}`,
      error: null,
      postInterviewScore: { fitTier: "strong", emotionalClassification: "neutral" },
    },
  ]);
});


test("one failed or empty model answer does not hide the other comparison answers", async () => {
  const results = await runInterviewComparison(
    {
      studyId: "study-01",
      personaId: "persona-07",
      question: "What matters most to you?",
      modelIds: [cheap.id, mid.id, expensive.id],
      allowExpensiveModels: true,
    },
    async () => {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: {
            interview_comparison: {
              results: [
                { model_id: cheap.id, answer: "Useful answer.", error: null },
                { model_id: mid.id, answer: null, error: "Provider unavailable." },
                { model_id: expensive.id, answer: "   ", error: null },
              ],
            },
          },
        }),
      };
    }
  );

  assert.deepEqual(results, [
    { modelId: cheap.id, answer: "Useful answer.", error: null, postInterviewScore: null },
    { modelId: mid.id, answer: null, error: "Provider unavailable.", postInterviewScore: null },
    {
      modelId: expensive.id,
      answer: null,
      error: "Model returned an empty answer.",
      postInterviewScore: null,
    },
  ]);
});


test("comparison repeats a backend budget error on every requested model", async () => {
  const results = await runInterviewComparison(
    {
      studyId: "study-01",
      personaId: "persona-07",
      question: "What matters most to you?",
      modelIds: [cheap.id, mid.id],
      allowExpensiveModels: false,
    },
    async () => {
      return {
        ok: false,
        status: 429,
        json: async () => ({ error: { code: "quota_exceeded", message: "Budget hard stop." } }),
      };
    }
  );

  assert.deepEqual(results, [
    { modelId: cheap.id, budgetStop: "Budget hard stop.", answer: null, error: "Budget hard stop.", postInterviewScore: null },
    { modelId: mid.id, budgetStop: "Budget hard stop.", answer: null, error: "Budget hard stop.", postInterviewScore: null },
  ]);
});


test("quota stop preserves completed comparison answers, regeneration IDs and scores", async () => {
  const results = await runInterviewComparison(
    {
      studyId: "study-01", personaId: "persona-07", question: "What matters?",
      modelIds: [mid.id, cheap.id], allowExpensiveModels: false,
    },
    async () => ({
      ok: false, status: 429,
      json: async () => ({ error: {
        code: "quota_exceeded", message: "Class budget hard stop.",
        details: { results: [{
          model_id: cheap.id, answer_id: "ans_completed", version: 0,
          answer: "Already paid answer.", error: null,
          post_interview_score: {
            fit_tier: "strong", emotional_classification: "positive",
            label: POST_INTERVIEW_SCORE_LABEL,
          },
        }] },
      } }),
    })
  );
  assert.deepEqual(results, [
    { modelId: mid.id, budgetStop: "Class budget hard stop.", answer: null, error: "Class budget hard stop.", postInterviewScore: null },
    {
      modelId: cheap.id, answerId: "ans_completed", version: 0,
      budgetStop: "Class budget hard stop.",
      answer: "Already paid answer.", error: null,
      postInterviewScore: { fitTier: "strong", emotionalClassification: "positive" },
    },
  ]);
});


test("comparison records a batch network failure against every requested model", async () => {
  const results = await runInterviewComparison(
    {
      studyId: "study-01",
      personaId: "persona-07",
      question: "What matters most to you?",
      modelIds: [cheap.id, mid.id],
      allowExpensiveModels: false,
    },
    async () => {
      throw new Error("Network unavailable.");
    }
  );

  assert.deepEqual(results, [
    { modelId: cheap.id, answer: null, error: "Network unavailable.", postInterviewScore: null },
    { modelId: mid.id, answer: null, error: "Network unavailable.", postInterviewScore: null },
  ]);

  const unknownFailures = await runInterviewComparison(
    {
      studyId: "study-01",
      personaId: "persona-07",
      question: "What matters most to you?",
      modelIds: [mid.id, cheap.id],
      allowExpensiveModels: false,
    },
    async () => {
      throw "offline";
    }
  );
  assert.deepEqual(unknownFailures, [
    {
      modelId: mid.id,
      answer: null,
      error: "Model comparison request failed.",
      postInterviewScore: null,
    },
    {
      modelId: cheap.id,
      answer: null,
      error: "Model comparison request failed.",
      postInterviewScore: null,
    },
  ]);
});


// Refuter round 5, F2: a budget stop that arrives with EVERY model already answered
// used to vanish — the per-card `error` only renders on a card with no answer, so the
// student blew the cap at the exact moment the app told them nothing was wrong.
test("budget stop survives when every requested model already answered", async () => {
  const results = await runInterviewComparison(
    {
      studyId: "study-01", personaId: "persona-07", question: "What matters?",
      modelIds: [cheap.id, mid.id], allowExpensiveModels: false,
    },
    async () => ({
      ok: false, status: 429,
      json: async () => ({ error: {
        code: "quota_exceeded", message: "Class budget hard stop.",
        details: { results: [
          { model_id: cheap.id, answer_id: "ans_a", version: 0, answer: "First paid answer.", error: null },
          { model_id: mid.id, answer_id: "ans_b", version: 0, answer: "Second paid answer.", error: null },
        ] },
      } }),
    })
  );

  assert.equal(results.length, 2);
  for (const result of results) {
    assert.equal(result.error, null, "a completed, charged answer must not read as an error");
    assert.ok(result.answer, "the paid answer must survive the budget stop");
    assert.equal(
      result.budgetStop,
      "Class budget hard stop.",
      "the budget stop must still reach the student when nothing else signals it"
    );
  }
});
