import { NextResponse } from "next/server";

import { toBackendReadinessPayload } from "@/lib/backend-readiness";
import { getServerApiBaseUrl } from "@/lib/server-env";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const READINESS_TIMEOUT_MS = 8000;

export async function GET() {
  let backendBaseUrl: string;
  try {
    backendBaseUrl = getServerApiBaseUrl();
  } catch (error) {
    return NextResponse.json(
      {
        ready: false,
        status: "misconfigured",
        message:
          error instanceof Error
            ? error.message
            : "Backend readiness is misconfigured.",
      },
      { status: 500 }
    );
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), READINESS_TIMEOUT_MS);

  try {
    const healthUrl = new URL("/api/v1/health", backendBaseUrl);
    const response = await fetch(healthUrl, {
      cache: "no-store",
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    const readiness = toBackendReadinessPayload(response.status, payload);

    return NextResponse.json(readiness, {
      status: readiness.ready ? 200 : 503,
    });
  } catch {
    return NextResponse.json(
      toBackendReadinessPayload(0, null),
      { status: 503 }
    );
  } finally {
    clearTimeout(timeout);
  }
}
