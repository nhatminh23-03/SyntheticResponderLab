import test from "node:test";
import assert from "node:assert/strict";

import { getDisplayApiErrorMessage } from "../src/lib/api";

test("getDisplayApiErrorMessage returns friendly quota copy", () => {
  assert.equal(
    getDisplayApiErrorMessage(429, "quota_exceeded", "fallback", "raw backend"),
    "You’ve reached today’s limit for this action. Please try again tomorrow or contact support."
  );
});

test("getDisplayApiErrorMessage returns friendly in-flight run copy", () => {
  assert.equal(
    getDisplayApiErrorMessage(409, "provider_run_in_flight", "fallback", "raw backend"),
    "You already have a run in progress. Wait for it to finish before starting another."
  );
});

test("getDisplayApiErrorMessage softens auth failures for the UI", () => {
  assert.equal(
    getDisplayApiErrorMessage(401, "unauthorized", "fallback", "raw backend"),
    "Your session has expired or you no longer have access. Please sign in again and retry."
  );
});

test("getDisplayApiErrorMessage keeps generic retry-later copy for unknown 429s", () => {
  assert.equal(
    getDisplayApiErrorMessage(429, "too_many_requests", "fallback", "raw backend"),
    "Too many requests right now. Please wait a moment and try again."
  );
});
