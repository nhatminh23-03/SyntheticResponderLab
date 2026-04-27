import { NextRequest, NextResponse } from "next/server";

import {
  getDeploymentSharedSecret,
  getServerApiBaseUrl,
  isClerkConfigured,
} from "@/lib/server-env";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const AUTH_HEADER_USER_ID = "x-authenticated-user-id";
const AUTH_HEADER_USER_EMAIL = "x-authenticated-user-email";
const AUTH_HEADER_AUTH_MODE = "x-authenticated-auth-mode";

function unauthorized() {
  return NextResponse.json(
    {
      error: {
        code: "unauthorized",
        message: "Authentication is required to use this application.",
      },
    },
    { status: 401 }
  );
}

async function resolveAuthHeaders():
  Promise<{ headers: Record<string, string> } | null> {
  if (!isClerkConfigured()) {
    // Legacy path — shared-password gate. Proxy the request without identity headers.
    // Backend will run without per-user enforcement in this mode.
    return { headers: { [AUTH_HEADER_AUTH_MODE]: "legacy-shared-password" } };
  }

  const { auth, clerkClient } = await import("@clerk/nextjs/server");
  const { userId } = await auth();
  if (!userId) {
    return null;
  }

  const headers: Record<string, string> = {
    [AUTH_HEADER_USER_ID]: userId,
    [AUTH_HEADER_AUTH_MODE]: "clerk",
  };

  try {
    const client = await clerkClient();
    const user = await client.users.getUser(userId);
    const primaryEmail = user.emailAddresses.find(
      (entry) => entry.id === user.primaryEmailAddressId
    )?.emailAddress;
    if (primaryEmail) {
      headers[AUTH_HEADER_USER_EMAIL] = primaryEmail;
    }
  } catch {
    // Silently continue without email; user id is sufficient for ownership checks.
  }

  return { headers };
}

async function forward(request: NextRequest, params: Promise<{ path: string[] }>) {
  const resolved = await resolveAuthHeaders();
  if (resolved === null) {
    return unauthorized();
  }

  const { path } = await params;
  const backendBaseUrl = getServerApiBaseUrl();
  const secret = getDeploymentSharedSecret();
  const targetUrl = new URL(`/${path.join("/")}`, backendBaseUrl);
  targetUrl.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  headers.delete("connection");

  // Strip any client-supplied identity headers to prevent spoofing through the proxy.
  headers.delete(AUTH_HEADER_USER_ID);
  headers.delete(AUTH_HEADER_USER_EMAIL);
  headers.delete(AUTH_HEADER_AUTH_MODE);

  if (secret) {
    headers.set("X-Deployment-Secret", secret);
  }

  for (const [key, value] of Object.entries(resolved.headers)) {
    headers.set(key, value);
  }

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : Buffer.from(await request.arrayBuffer());

  const upstream = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    redirect: "manual",
    cache: "no-store",
  });

  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  responseHeaders.delete("transfer-encoding");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward(request, context.params);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward(request, context.params);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward(request, context.params);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward(request, context.params);
}
