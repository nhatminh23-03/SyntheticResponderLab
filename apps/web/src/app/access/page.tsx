import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  ACCESS_COOKIE_NAME,
  hasValidAccessCookie,
  isAppAccessGateEnabled,
  normalizeReturnTo,
} from "@/lib/access-control";

type AccessPageProps = {
  searchParams?: {
    error?: string;
    returnTo?: string;
  };
};

function getErrorMessage(error?: string) {
  if (error === "invalid") {
    return "That password was not recognized. Please try again.";
  }
  return null;
}

export default async function AccessPage({ searchParams }: AccessPageProps) {
  const returnTo = normalizeReturnTo(searchParams?.returnTo);
  if (!isAppAccessGateEnabled()) {
    redirect(returnTo);
  }

  const cookieStore = cookies();
  const alreadyAuthorized = await hasValidAccessCookie(
    cookieStore.get(ACCESS_COOKIE_NAME)?.value ?? null
  );
  if (alreadyAuthorized) {
    redirect(returnTo);
  }

  const errorMessage = getErrorMessage(searchParams?.error);

  return (
    <main className="min-h-screen bg-[var(--color-canvas)] px-4 py-10 text-[var(--color-ink)] sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-md items-center">
        <div className="w-full rounded-[2rem] border border-[var(--color-border-soft)] bg-[var(--color-panel)]/90 p-6 shadow-[0_24px_80px_rgba(5,12,18,0.28)] backdrop-blur-xl sm:p-8">
          <div className="mb-8">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.32em] text-[var(--color-accent)]">
              Protected Access
            </div>
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--color-ink)]">
              Enter the deployment password
            </h1>
            <p className="mt-3 text-sm leading-7 text-[var(--color-ink-muted)] sm:text-[15px]">
              This deployment is protected to prevent anonymous public access to
              study creation, uploads, and provider-backed runs.
            </p>
          </div>

          {errorMessage ? (
            <div className="mb-5 rounded-[1.2rem] border border-[var(--color-warning-border)] bg-[var(--color-warning-soft)] px-4 py-3 text-sm text-[var(--color-warning-ink)]">
              {errorMessage}
            </div>
          ) : null}

          <form
            action="/api/access/login"
            method="post"
            className="space-y-4"
          >
            <input type="hidden" name="returnTo" value={returnTo} />
            <label className="block">
              <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-ink-muted)]">
                Password
              </span>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                className="w-full rounded-[1.2rem] border border-[var(--color-border-soft)] bg-[var(--color-canvas)]/70 px-4 py-3 text-base text-[var(--color-ink)] outline-none transition focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/20"
                placeholder="Enter deployment password"
                required
              />
            </label>
            <button
              type="submit"
              className="inline-flex w-full items-center justify-center rounded-[1.2rem] bg-[var(--color-accent)] px-4 py-3 text-sm font-semibold text-[var(--color-accent-contrast)] transition hover:brightness-105"
            >
              Continue to app
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
