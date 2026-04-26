const LEGACY_PUBLIC_API_ENV = "NEXT_PUBLIC_API_BASE_URL";
const LOCAL_DEV_API_BASE_URL = "http://127.0.0.1:8000";

export function isLocalDevelopmentEnvironment() {
  return (process.env.NODE_ENV || "development") === "development";
}

function normalizeUrl(name: string, value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(`${name} must be a valid absolute http(s) URL.`);
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`${name} must use http or https.`);
  }

  parsed.pathname = parsed.pathname.replace(/\/$/, "");
  return parsed.toString().replace(/\/$/, "");
}

export function getServerApiBaseUrl() {
  const apiBaseUrl = process.env.API_BASE_URL?.trim();
  const legacyPublicApiBaseUrl = process.env[LEGACY_PUBLIC_API_ENV]?.trim();

  if (apiBaseUrl) {
    return normalizeUrl("API_BASE_URL", apiBaseUrl);
  }

  if (legacyPublicApiBaseUrl) {
    return normalizeUrl(LEGACY_PUBLIC_API_ENV, legacyPublicApiBaseUrl);
  }

  if (isLocalDevelopmentEnvironment()) {
    return LOCAL_DEV_API_BASE_URL;
  }

  throw new Error(
    "Missing required backend origin. Set API_BASE_URL (preferred) or NEXT_PUBLIC_API_BASE_URL. Production-like environments do not default to localhost."
  );
}

export function getDeploymentSharedSecret() {
  const trimmed = process.env.DEPLOYMENT_SHARED_SECRET?.trim() || "";
  if (trimmed) {
    return trimmed;
  }

  if (isLocalDevelopmentEnvironment()) {
    return "";
  }

  throw new Error(
    "Missing required environment variable: DEPLOYMENT_SHARED_SECRET. Production-like environments must configure the frontend proxy secret."
  );
}

export function getAppAccessPassword() {
  const trimmed = process.env.APP_ACCESS_PASSWORD?.trim() || "";
  if (trimmed) {
    if (!isLocalDevelopmentEnvironment() && trimmed.length < 12) {
      throw new Error(
        "APP_ACCESS_PASSWORD must be at least 12 characters in production-like environments."
      );
    }
    return trimmed;
  }

  return "";
}

export function isClerkConfigured() {
  return (
    (process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim() || "") !== "" &&
    (process.env.CLERK_SECRET_KEY?.trim() || "") !== ""
  );
}

export function getClerkPublishableKey() {
  return process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim() || "";
}

export function getClerkSecretKey() {
  return process.env.CLERK_SECRET_KEY?.trim() || "";
}

export function assertProductionAuthConfigured() {
  if (isLocalDevelopmentEnvironment()) {
    return;
  }

  const hasClerk = isClerkConfigured();
  const hasLegacyGate = getAppAccessPassword() !== "";

  if (!hasClerk && !hasLegacyGate) {
    throw new Error(
      "Missing required authentication configuration. Production-like environments must configure Clerk (NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY + CLERK_SECRET_KEY) or, as a standalone fallback, APP_ACCESS_PASSWORD."
    );
  }

  if (process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim() && !process.env.CLERK_SECRET_KEY?.trim()) {
    throw new Error(
      "Clerk is partially configured. CLERK_SECRET_KEY is required when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is set."
    );
  }

  if (process.env.CLERK_SECRET_KEY?.trim() && !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim()) {
    throw new Error(
      "Clerk is partially configured. NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is required when CLERK_SECRET_KEY is set."
    );
  }
}
