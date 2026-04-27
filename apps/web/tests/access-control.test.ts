import test from "node:test";
import assert from "node:assert/strict";

import { normalizeReturnTo } from "../src/lib/access-control";

test("normalizeReturnTo keeps safe in-app paths", () => {
  assert.equal(normalizeReturnTo("/survey?step=1"), "/survey?step=1");
});

test("normalizeReturnTo rejects external-like destinations", () => {
  assert.equal(normalizeReturnTo("https://example.com"), "/");
  assert.equal(normalizeReturnTo("//evil.example.com"), "/");
  assert.equal(normalizeReturnTo("javascript:alert(1)"), "/");
  assert.equal(normalizeReturnTo(""), "/");
});
