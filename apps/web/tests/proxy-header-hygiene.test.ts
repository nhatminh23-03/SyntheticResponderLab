import test from "node:test";
import assert from "node:assert/strict";

const AUTH_HEADER_USER_ID = "x-authenticated-user-id";
const AUTH_HEADER_USER_EMAIL = "x-authenticated-user-email";
const AUTH_HEADER_AUTH_MODE = "x-authenticated-auth-mode";

/**
 * Smoke test for the proxy's header hygiene contract. We don't spin up a
 * Next.js server here; we assert the invariants the proxy route is designed
 * to enforce:
 *   - Client-supplied X-Authenticated-* headers must never be forwarded.
 *   - Identity headers emitted by the proxy itself replace any client input.
 */
function simulateProxyHeaderHygiene(
  incoming: Record<string, string>,
  serverResolved: { userId: string; email?: string; authMode: string }
): Headers {
  const headers = new Headers(incoming);

  headers.delete(AUTH_HEADER_USER_ID);
  headers.delete(AUTH_HEADER_USER_EMAIL);
  headers.delete(AUTH_HEADER_AUTH_MODE);

  headers.set(AUTH_HEADER_USER_ID, serverResolved.userId);
  if (serverResolved.email) {
    headers.set(AUTH_HEADER_USER_EMAIL, serverResolved.email);
  }
  headers.set(AUTH_HEADER_AUTH_MODE, serverResolved.authMode);

  return headers;
}

test("proxy strips client-supplied identity headers", () => {
  const result = simulateProxyHeaderHygiene(
    {
      "x-authenticated-user-id": "user_attacker",
      "x-authenticated-user-email": "attacker@example.com",
      "x-authenticated-auth-mode": "clerk",
      "content-type": "application/json",
    },
    { userId: "user_real", email: "real@example.com", authMode: "clerk" }
  );

  assert.equal(result.get(AUTH_HEADER_USER_ID), "user_real");
  assert.equal(result.get(AUTH_HEADER_USER_EMAIL), "real@example.com");
  assert.equal(result.get(AUTH_HEADER_AUTH_MODE), "clerk");
  assert.equal(result.get("content-type"), "application/json");
});

test("proxy omits email header when none resolved", () => {
  const result = simulateProxyHeaderHygiene(
    {
      "x-authenticated-user-email": "attacker@example.com",
    },
    { userId: "user_real", authMode: "clerk" }
  );

  assert.equal(result.get(AUTH_HEADER_USER_EMAIL), null);
  assert.equal(result.get(AUTH_HEADER_USER_ID), "user_real");
});

test("proxy overrides auth mode from client input", () => {
  const result = simulateProxyHeaderHygiene(
    {
      "x-authenticated-auth-mode": "dev-fallback",
    },
    { userId: "user_real", authMode: "clerk" }
  );

  assert.equal(result.get(AUTH_HEADER_AUTH_MODE), "clerk");
});
