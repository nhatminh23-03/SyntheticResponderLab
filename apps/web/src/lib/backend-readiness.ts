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
