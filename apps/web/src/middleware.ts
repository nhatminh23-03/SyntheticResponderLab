import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { clerkMiddleware } from "@clerk/nextjs/server";

import {
  ACCESS_COOKIE_NAME,
  hasValidAccessCookie,
  isAppAccessGateEnabled,
} from "./lib/access-control";
import {
  CLASSROOM_SESSION_COOKIE_NAME,
  isClassroomInterviewApiRequest,
  isClassroomInterviewPage,
  isClassroomNoLoginEnabled,
  isValidClassroomSessionId,
} from "./lib/classroom-access";

const isClerkConfigured =
  (process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.trim() || "") !== "" &&
  (process.env.CLERK_SECRET_KEY?.trim() || "") !== "";

const isAlwaysPublicPath = (pathname: string) =>
  pathname.startsWith("/_next/") ||
  pathname === "/favicon.ico" ||
  pathname === "/api/readiness" ||
  pathname.startsWith("/access") ||
  pathname.startsWith("/api/access/");

function unauthorizedApiResponse() {
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

function classroomAccessResponse(request: NextRequest) {
  if (!isClassroomNoLoginEnabled()) {
    return null;
  }

  const { pathname } = request.nextUrl;
  const sessionId = request.cookies.get(CLASSROOM_SESSION_COOKIE_NAME)?.value;

  if (isClassroomInterviewPage(pathname)) {
    const response = NextResponse.next();
    if (!isValidClassroomSessionId(sessionId)) {
      response.cookies.set(CLASSROOM_SESSION_COOKIE_NAME, crypto.randomUUID(), {
        httpOnly: true,
        sameSite: "lax",
        secure: request.nextUrl.protocol === "https:",
        path: "/",
        maxAge: 60 * 60 * 12,
      });
    }
    return response;
  }

  if (
    isClassroomInterviewApiRequest(pathname, request.method) &&
    isValidClassroomSessionId(sessionId)
  ) {
    return NextResponse.next();
  }

  return null;
}

async function runLegacyGate(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  const classroomResponse = classroomAccessResponse(request);
  if (classroomResponse) {
    return classroomResponse;
  }

  if (isAlwaysPublicPath(pathname)) {
    return NextResponse.next();
  }

  let gateEnabled = false;
  try {
    gateEnabled = isAppAccessGateEnabled();
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Application access-control is misconfigured.";
    return new NextResponse(message, { status: 500 });
  }

  if (!gateEnabled) {
    return NextResponse.next();
  }

  const hasAccess = await hasValidAccessCookie(
    request.cookies.get(ACCESS_COOKIE_NAME)?.value ?? null
  );
  if (hasAccess) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/backend/")) {
    return unauthorizedApiResponse();
  }

  const destination = new URL("/access", request.url);
  destination.searchParams.set("returnTo", `${pathname}${search}`);
  return NextResponse.redirect(destination);
}

/**
 * Clerk mode: do not redirect anonymous users away from `/` or other marketing
 * routes. The home page uses <SignedOut>/<SignedIn> to swap PublicLandingShell
 * vs the full AppShell. Only the server proxy to FastAPI requires a session.
 */
const composed = isClerkConfigured
  ? clerkMiddleware(async (auth, request) => {
      const { pathname } = request.nextUrl;

      const classroomResponse = classroomAccessResponse(request);
      if (classroomResponse) {
        return classroomResponse;
      }

      if (pathname.startsWith("/api/backend/")) {
        const { userId } = await auth();
        if (!userId) {
          return unauthorizedApiResponse();
        }
      }

      return NextResponse.next();
    })
  : async (request: NextRequest) => runLegacyGate(request);

export default composed;

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
    "/api/backend/:path*",
  ],
};
