"use client";

import { PropsWithChildren } from "react";

import { Button } from "@/components/ui/button";
import { HeroSignalPanel } from "@/components/sections/hero-signal-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import type { BackendReadinessState } from "@/hooks/use-backend-readiness";
import { useBackendReadiness } from "@/hooks/use-backend-readiness";

type BackendReadinessNoticeProps = {
  className?: string;
  readiness: BackendReadinessState;
};

export function BackendReadinessNotice({
  className = "",
  readiness,
}: BackendReadinessNoticeProps) {
  if (readiness.ready) {
    return null;
  }

  return (
    <div
      className={`rounded-2xl border px-4 py-3 text-sm [background:var(--panel-bg-soft)] [border-color:var(--panel-border)] ${className}`}
      role={readiness.status === "unavailable" ? "alert" : "status"}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-app-cyan shadow-[0_0_18px_rgba(91,225,255,0.55)]" />
          <div>
            <div className="font-medium text-app-text">
              {readiness.status === "unavailable"
                ? "Backend still waking"
                : "Starting backend"}
            </div>
            <div className="mt-1 text-app-muted">{readiness.message}</div>
          </div>
        </div>
        {readiness.status === "unavailable" ? (
          <Button
            variant="secondary"
            onClick={readiness.retry}
            disabled={readiness.isChecking}
            className="h-10 shrink-0 px-4 py-2"
          >
            Retry
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function BackendReadinessGate({ children }: PropsWithChildren) {
  const readiness = useBackendReadiness();

  if (readiness.ready) {
    return <>{children}</>;
  }

  return (
    <div className="relative min-h-screen overflow-x-clip bg-app-bg text-app-text">
      <div className="pointer-events-none fixed inset-0">
        <div
          className="absolute inset-x-0 top-0 h-[32rem]"
          style={{ background: "var(--app-backdrop-top)" }}
        />
        <div
          className="absolute right-[-9rem] top-[10rem] h-[24rem] w-[24rem] rounded-full blur-3xl"
          style={{ background: "var(--app-backdrop-gold)" }}
        />
        <div
          className="absolute left-[-12rem] top-[34rem] h-[26rem] w-[26rem] rounded-full blur-3xl"
          style={{ background: "var(--app-backdrop-cyan)" }}
        />
      </div>

      <main className="relative mx-auto grid min-h-screen w-full max-w-[88rem] gap-8 px-4 py-8 sm:px-6 md:px-8 lg:grid-cols-[minmax(0,0.95fr)_minmax(22rem,0.85fr)] lg:items-center lg:px-12 xl:px-16">
        <RevealOnScroll className="max-w-2xl">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-app-cyan/20 bg-app-cyan/5 px-3 py-1.5 text-[0.62rem] font-medium uppercase tracking-[0.22em] text-app-cyan">
            <span className="h-1.5 w-1.5 rounded-full bg-app-cyan" />
            Preparing workspace
          </div>

          <h1 className="font-display text-[2.65rem] font-medium leading-[0.96] tracking-[-0.055em] text-app-text sm:text-[3.2rem] md:text-[4rem]">
            Starting your research workspace
          </h1>
          <p className="mt-4 max-w-xl text-[1rem] leading-7 text-app-muted">
            The backend may need a moment to wake up. Your session is ready,
            and the workflow will open as soon as the API is available.
          </p>

          <BackendReadinessNotice
            className="mt-6 max-w-xl"
            readiness={readiness}
          />
        </RevealOnScroll>

        <RevealOnScroll delay={0.08}>
          <HeroSignalPanel />
        </RevealOnScroll>
      </main>
    </div>
  );
}
