import { getAppAccessPassword, getDeploymentSharedSecret } from "./server-env";

export const ACCESS_COOKIE_NAME = "synthetic_responder_access";

function encodeHex(bytes: Uint8Array) {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256(value: string) {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return encodeHex(new Uint8Array(digest));
}

export function isAppAccessGateEnabled() {
  return getAppAccessPassword() !== "";
}

export function normalizeReturnTo(input?: string | null) {
  const candidate = (input || "").trim();
  if (!candidate.startsWith("/") || candidate.startsWith("//")) {
    return "/";
  }
  return candidate;
}

export async function getExpectedAccessCookieValue() {
  const password = getAppAccessPassword();
  if (!password) {
    return "";
  }
  const deploymentSecret = getDeploymentSharedSecret() || "local-development-access";
  return sha256(`synthetic-responder-access:${password}:${deploymentSecret}`);
}

export async function hasValidAccessCookie(cookieValue?: string | null) {
  if (!isAppAccessGateEnabled()) {
    return true;
  }
  if (!cookieValue) {
    return false;
  }
  const expected = await getExpectedAccessCookieValue();
  return cookieValue === expected;
}

export async function getAccessCookieValueForPassword(submittedPassword: string) {
  const configuredPassword = getAppAccessPassword();
  if (!configuredPassword) {
    return "";
  }
  if (submittedPassword !== configuredPassword) {
    return null;
  }
  return getExpectedAccessCookieValue();
}
