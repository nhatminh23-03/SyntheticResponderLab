import test from "node:test";
import assert from "node:assert/strict";

import { getInterviewModelCatalog, getInterviewPersonas } from "../src/lib/api";


test("getInterviewPersonas loads the FastAPI persona endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = (async (input, init) => {
    requestedUrl = String(input);
    assert.equal(init?.method, "GET");
    return new Response(
      JSON.stringify({
        data: {
          source: "database",
          personas: [{ persona_id: "P001", lifestyle_tags: [] }],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }) as typeof fetch;

  try {
    const result = await getInterviewPersonas();
    assert.equal(requestedUrl, "/api/backend/api/v1/personas");
    assert.equal(result.source, "database");
    assert.equal(result.personas[0]?.persona_id, "P001");
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("getInterviewPersonas reports backend errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({ error: { code: "database_error", message: "Persona database unavailable." } }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    )) as typeof fetch;

  try {
    await assert.rejects(getInterviewPersonas(), /Persona database unavailable/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("getInterviewModelCatalog loads curated prices from FastAPI", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = (async (input, init) => {
    requestedUrl = String(input);
    assert.equal(init?.method, "GET");
    return new Response(
      JSON.stringify({
        data: {
          source: "curated",
          pricing_as_of: "2026-09-04",
          pricing_source: "https://openrouter.ai/api/v1/models",
          default_model_id: "provider/cheap",
          persona_count: { minimum: 3, default: 3, maximum: 30 },
          cost_estimate: {
            prompt_tokens_per_model_persona: 10000,
            completion_tokens_per_model_persona: 2000,
          },
          models: [
            {
              id: "provider/cheap",
              name: "Cheap Model",
              tier: "cheap",
              prompt_price_per_million: 0.1,
              completion_price_per_million: 0.4,
              estimated_cost_per_persona_usd: 0.0018,
            },
          ],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }) as typeof fetch;

  try {
    const result = await getInterviewModelCatalog();
    assert.equal(requestedUrl, "/api/backend/api/v1/interview/models");
    assert.equal(result.defaultModelId, "provider/cheap");
    assert.equal(result.models[0]?.completion_price_per_million, 0.4);
    assert.deepEqual(result.personaCount, { minimum: 3, default: 3, maximum: 30 });
    assert.equal(result.costEstimate.prompt_tokens_per_model_persona, 10000);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("getInterviewModelCatalog rejects persona-count bounds outside the 3-to-30 contract", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        data: {
          source: "curated",
          default_model_id: "provider/cheap",
          persona_count: { minimum: 1, default: 1, maximum: 30 },
          cost_estimate: {
            prompt_tokens_per_model_persona: 10000,
            completion_tokens_per_model_persona: 2000,
          },
          models: [
            {
              id: "provider/cheap",
              name: "Cheap Model",
              tier: "cheap",
              prompt_price_per_million: 0.1,
              completion_price_per_million: 0.4,
              estimated_cost_per_persona_usd: 0.0018,
            },
          ],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    )) as typeof fetch;

  try {
    await assert.rejects(
      getInterviewModelCatalog(),
      /invalid interview model catalog/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("getInterviewModelCatalog rejects a successful response without usable selections", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        data: {
          source: "curated",
          default_model_id: "provider/missing",
          models: [],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    )) as typeof fetch;

  try {
    await assert.rejects(
      getInterviewModelCatalog(),
      /invalid interview model catalog/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
