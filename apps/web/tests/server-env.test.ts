import test from "node:test";
import assert from "node:assert/strict";

import {
  assertProductionAuthConfigured,
  getAppAccessPassword,
  getDeploymentSharedSecret,
  getServerApiBaseUrl,
  isClerkConfigured,
} from "../src/lib/server-env";

function restoreEnv(name: string, value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

function withEnv(
  overrides: Record<string, string | undefined>,
  fn: () => void
) {
  const original: Record<string, string | undefined> = {};
  for (const key of Object.keys(overrides)) {
    original[key] = process.env[key];
    const value = overrides[key];
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
  try {
    fn();
  } finally {
    for (const key of Object.keys(overrides)) {
      restoreEnv(key, original[key]);
    }
  }
}

test("getServerApiBaseUrl prefers API_BASE_URL", () => {
  withEnv(
    {
      API_BASE_URL: "https://api.example.com",
      NEXT_PUBLIC_API_BASE_URL: "https://public.example.com",
    },
    () => {
      assert.equal(getServerApiBaseUrl(), "https://api.example.com");
    }
  );
});

test("getServerApiBaseUrl falls back to NEXT_PUBLIC_API_BASE_URL only when needed", () => {
  withEnv(
    {
      API_BASE_URL: undefined,
      NEXT_PUBLIC_API_BASE_URL: "https://public.example.com",
      NODE_ENV: "production",
    },
    () => {
      assert.equal(getServerApiBaseUrl(), "https://public.example.com");
    }
  );
});

test("getServerApiBaseUrl uses local fallback only in development", () => {
  withEnv(
    {
      API_BASE_URL: undefined,
      NEXT_PUBLIC_API_BASE_URL: undefined,
      NODE_ENV: "development",
    },
    () => {
      assert.equal(getServerApiBaseUrl(), "http://127.0.0.1:8000");
    }
  );
});

test("getServerApiBaseUrl throws when no backend base URL is configured in production", () => {
  withEnv(
    {
      API_BASE_URL: undefined,
      NEXT_PUBLIC_API_BASE_URL: undefined,
      NODE_ENV: "production",
    },
    () => {
      assert.throws(
        () => getServerApiBaseUrl(),
        /Production-like environments do not default to localhost/
      );
    }
  );
});

test("getServerApiBaseUrl throws on invalid URL", () => {
  withEnv(
    {
      API_BASE_URL: "not-a-url",
      NEXT_PUBLIC_API_BASE_URL: undefined,
      NODE_ENV: "production",
    },
    () => {
      assert.throws(
        () => getServerApiBaseUrl(),
        /valid absolute http\(s\) URL/
      );
    }
  );
});

test("getDeploymentSharedSecret returns empty string when unset in development", () => {
  withEnv(
    { DEPLOYMENT_SHARED_SECRET: undefined, NODE_ENV: "development" },
    () => {
      assert.equal(getDeploymentSharedSecret(), "");
    }
  );
});

test("getDeploymentSharedSecret throws when unset in production", () => {
  withEnv(
    { DEPLOYMENT_SHARED_SECRET: undefined, NODE_ENV: "production" },
    () => {
      assert.throws(
        () => getDeploymentSharedSecret(),
        /DEPLOYMENT_SHARED_SECRET/
      );
    }
  );
});

test("getAppAccessPassword returns empty string when unset", () => {
  withEnv(
    { APP_ACCESS_PASSWORD: undefined, NODE_ENV: "development" },
    () => {
      assert.equal(getAppAccessPassword(), "");
    }
  );
});

test("getAppAccessPassword returns empty string when unset in production (now optional)", () => {
  withEnv(
    { APP_ACCESS_PASSWORD: undefined, NODE_ENV: "production" },
    () => {
      assert.equal(getAppAccessPassword(), "");
    }
  );
});

test("getAppAccessPassword rejects short production passwords when set", () => {
  withEnv(
    { APP_ACCESS_PASSWORD: "too-short", NODE_ENV: "production" },
    () => {
      assert.throws(
        () => getAppAccessPassword(),
        /at least 12 characters/
      );
    }
  );
});

test("isClerkConfigured reports false when keys are missing", () => {
  withEnv(
    {
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
      CLERK_SECRET_KEY: undefined,
    },
    () => {
      assert.equal(isClerkConfigured(), false);
    }
  );
});

test("isClerkConfigured reports true when both keys are set", () => {
  withEnv(
    {
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_abc",
      CLERK_SECRET_KEY: "sk_test_abc",
    },
    () => {
      assert.equal(isClerkConfigured(), true);
    }
  );
});

test("assertProductionAuthConfigured throws in production without Clerk or APP_ACCESS_PASSWORD", () => {
  withEnv(
    {
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
      CLERK_SECRET_KEY: undefined,
      APP_ACCESS_PASSWORD: undefined,
    },
    () => {
      assert.throws(
        () => assertProductionAuthConfigured(),
        /authentication configuration/
      );
    }
  );
});

test("assertProductionAuthConfigured passes in production with Clerk configured", () => {
  withEnv(
    {
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_abc",
      CLERK_SECRET_KEY: "sk_test_abc",
      APP_ACCESS_PASSWORD: undefined,
    },
    () => {
      assert.doesNotThrow(() => assertProductionAuthConfigured());
    }
  );
});

test("assertProductionAuthConfigured passes in production with APP_ACCESS_PASSWORD only", () => {
  withEnv(
    {
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
      CLERK_SECRET_KEY: undefined,
      APP_ACCESS_PASSWORD: "legacy-gate-password-123",
    },
    () => {
      assert.doesNotThrow(() => assertProductionAuthConfigured());
    }
  );
});

test("assertProductionAuthConfigured rejects partial Clerk configuration", () => {
  withEnv(
    {
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_abc",
      CLERK_SECRET_KEY: undefined,
      APP_ACCESS_PASSWORD: "legacy-gate-password-123",
    },
    () => {
      assert.throws(
        () => assertProductionAuthConfigured(),
        /CLERK_SECRET_KEY is required/
      );
    }
  );
});
