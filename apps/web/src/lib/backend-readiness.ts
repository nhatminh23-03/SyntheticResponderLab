import { JEV_MODEL_ID } from "./experiment-models";

export type BackendReadinessPayload = {
  ready: boolean;
  status: "ready" | "waking" | "unavailable" | "misconfigured";
  healthStatus?: "ok" | "degraded" | "failed" | string;
  message: string;
  providers?: { jev: boolean; openrouter: boolean };
};

type HealthEnvelope = {
  data?: {
    status?: string;
    providers?: { jev?: boolean; openrouter?: boolean };
  };
};

export function toBackendReadinessPayload(
  httpStatus: number,
  payload: unknown
): BackendReadinessPayload {
  const healthStatus =
    typeof payload === "object" && payload !== null
      ? (payload as HealthEnvelope).data?.status
      : undefined;
  const rawProviders = typeof payload === "object" && payload !== null ? (payload as HealthEnvelope).data?.providers : undefined;
  const providers = rawProviders ? { jev: Boolean(rawProviders.jev), openrouter: Boolean(rawProviders.openrouter) } : undefined;

  if (httpStatus >= 200 && httpStatus < 300) {
    if (healthStatus === "ok" || healthStatus === "degraded") {
      return {
        ready: true,
        status: "ready",
        healthStatus,
        message: "Backend is ready.",
        providers,
      };
    }

    if (healthStatus === "failed") {
      return {
        ready: false,
        status: "unavailable",
        healthStatus,
        message:
          "The backend is online but not ready yet. Please retry in a moment.",
        providers,
      };
    }
  }

  if (httpStatus === 503 || httpStatus === 504 || httpStatus === 0) {
    return {
      ready: false,
      status: "waking",
      healthStatus,
      message: "Starting backend... this may take up to a minute.",
      providers,
    };
  }

  return {
    ready: false,
    status: "unavailable",
    healthStatus,
    message: "The backend is not ready yet. Please retry in a moment.",
    providers,
  };
}

export function liveEngineAvailable(readiness: BackendReadinessPayload | null | undefined): boolean {
  return Boolean(readiness?.providers && (readiness.providers.jev || readiness.providers.openrouter));
}

export const STUDY_MODELS_NEED_A_KEY =
  "This study's models need a key this server does not have — use the preloaded demo or switch models in the Experiment step.";
export const DEMO_NEEDS_UPDATED_API = "Demo needs the updated API.";

export type RunControl = { enabled: boolean; hint: string | null };

/** True when the study is saved to run on Jev alone (the only plan the API sends to Jev). */
export function isJevOnlyPlan(selectedModels: string[] | null | undefined): boolean {
  return Array.isArray(selectedModels) && selectedModels.length === 1 && selectedModels[0] === JEV_MODEL_ID;
}

/**
 * The Run live button follows the study's saved models, not the server: "(Jev)" only for a Jev-only plan, and
 * enabled only when the server is ready and has the key that plan needs (Jev → providers.jev, else → providers.openrouter).
 */
export function liveRunControl(
  selectedModels: string[] | null | undefined,
  readiness: BackendReadinessPayload | null | undefined
): RunControl & { label: string } {
  const jevPlan = isJevOnlyPlan(selectedModels);
  const label = jevPlan ? "Run live (Jev)" : "Run live";
  if (!readiness) {
    return {
      label,
      enabled: false,
      hint: "Could not check which AI engines this server has, so Run live and the preloaded demo are unavailable. Reload to try again.",
    };
  }
  if (!readiness.ready) {
    return {
      label,
      enabled: false,
      hint: readiness.providers
        ? "The backend is not ready yet, so Run live is unavailable. Use the preloaded demo, or try again in a moment."
        : "The backend is not ready yet, so Run live and the preloaded demo are unavailable. Reload the page in a moment.",
    };
  }
  if (!readiness.providers) return { label, enabled: false, hint: "Run live needs the updated API." };
  if (!readiness.providers.jev && !readiness.providers.openrouter) {
    return { label, enabled: false, hint: "No AI key on this server — use the preloaded demo." };
  }
  const hasKey = jevPlan ? readiness.providers.jev : readiness.providers.openrouter;
  return hasKey ? { label, enabled: true, hint: null } : { label, enabled: false, hint: STUDY_MODELS_NEED_A_KEY };
}

/**
 * The preloaded demo needs an API that honours `source`; only that API reports `providers`. An older API would
 * ignore {source: "demo"} and start a paid live run, so the button stays off until `providers` is present.
 */
export function demoRunControl(readiness: BackendReadinessPayload | null | undefined): RunControl {
  if (readiness?.providers) return { enabled: true, hint: null };
  // When readiness is unknown or the backend is not ready, the Run live hint already says why both are off.
  return { enabled: false, hint: readiness?.ready ? DEMO_NEEDS_UPDATED_API : null };
}

export const READINESS_RECHECK_INTERVAL_MS = 5000;
export const READINESS_RECHECK_WINDOW_MS = 120000;
export const WAKING_SERVER_HINT = "Waking the server — buttons turn on in a moment.";

/**
 * Ruling R19: a cold start must not leave the Run step's buttons off until a reload. Check readiness again while the
 * payload is missing, not ready, or lacks `providers`, for at most READINESS_RECHECK_WINDOW_MS since checking began.
 */
export function shouldRecheckReadiness(
  readiness: BackendReadinessPayload | null | undefined,
  elapsedMs: number
): boolean {
  if (readiness?.ready && readiness.providers) return false;
  return elapsedMs < READINESS_RECHECK_WINDOW_MS;
}
