import { NextResponse } from "next/server";

import {
  ACCESS_COOKIE_NAME,
  getAccessCookieValueForPassword,
  normalizeReturnTo,
} from "@/lib/access-control";

function buildRedirect(request: Request, pathname: string, params?: Record<string, string>) {
  const destination = new URL(pathname, request.url);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      destination.searchParams.set(key, value);
    });
  }
  return destination;
}

export async function POST(request: Request) {
  const formData = await request.formData();
  const submittedPassword = String(formData.get("password") || "");
  const returnTo = normalizeReturnTo(String(formData.get("returnTo") || "/"));
  const cookieValue = await getAccessCookieValueForPassword(submittedPassword);

  if (cookieValue === null) {
    return NextResponse.redirect(
      buildRedirect(request, "/access", {
        error: "invalid",
        returnTo,
      }),
      { status: 303 }
    );
  }

  const response = NextResponse.redirect(buildRedirect(request, returnTo), {
    status: 303,
  });
  if (cookieValue) {
    response.cookies.set({
      name: ACCESS_COOKIE_NAME,
      value: cookieValue,
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 12,
    });
  }
  return response;
}
