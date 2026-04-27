export type BackendReadinessPayload = {
  ready: boolean;
  status: "ready" | "waking" | "unavailable" | "misconfigured";
  healthStatus?: "ok" | "degraded" | "failed" | string;
  message: string;
};

type HealthEnvelope = {
  data?: {
    status?: string;
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

  if (httpStatus >= 200 && httpStatus < 300) {
    if (healthStatus === "ok" || healthStatus === "degraded") {
      return {
        ready: true,
        status: "ready",
        healthStatus,
        message: "Backend is ready.",
      };
    }

    if (healthStatus === "failed") {
      return {
        ready: false,
        status: "unavailable",
        healthStatus,
        message:
          "The backend is online but not ready yet. Please retry in a moment.",
      };
    }
  }

  if (httpStatus === 503 || httpStatus === 504 || httpStatus === 0) {
    return {
      ready: false,
      status: "waking",
      healthStatus,
      message: "Starting backend... this may take up to a minute.",
    };
  }

  return {
    ready: false,
    status: "unavailable",
    healthStatus,
    message: "The backend is not ready yet. Please retry in a moment.",
  };
}
