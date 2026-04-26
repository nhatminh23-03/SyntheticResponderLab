import test from "node:test";
import assert from "node:assert/strict";

import { toBackendReadinessPayload } from "../src/lib/backend-readiness";

test("backend readiness accepts ok health", () => {
  const payload = toBackendReadinessPayload(200, {
    data: { status: "ok" },
  });

  assert.equal(payload.ready, true);
  assert.equal(payload.status, "ready");
});

test("backend readiness accepts degraded health as usable", () => {
  const payload = toBackendReadinessPayload(200, {
    data: { status: "degraded" },
  });

  assert.equal(payload.ready, true);
  assert.equal(payload.status, "ready");
});

test("backend readiness treats timeout-shaped failures as waking", () => {
  const payload = toBackendReadinessPayload(0, null);

  assert.equal(payload.ready, false);
  assert.equal(payload.status, "waking");
});

test("backend readiness treats failed health as unavailable", () => {
  const payload = toBackendReadinessPayload(200, {
    data: { status: "failed" },
  });

  assert.equal(payload.ready, false);
  assert.equal(payload.status, "unavailable");
});
