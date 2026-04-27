"use client";

import Link from "next/link";

import { BackendReadinessNotice } from "@/components/ui/backend-readiness";
import { Button } from "@/components/ui/button";
import { HeroSignalPanel } from "@/components/sections/hero-signal-panel";
import { MetricPill } from "@/components/ui/metric-pill";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { useBackendReadiness } from "@/hooks/use-backend-readiness";

export function PublicLandingShell() {
  const readiness = useBackendReadiness();

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

      <PublicTopNav backendReady={readiness.ready} />

      <main className="relative mx-auto flex min-h-[calc(100vh-5.5rem)] w-full max-w-[88rem] flex-col px-4 pb-14 pt-8 sm:min-h-[calc(100vh-var(--nav-height))] sm:px-5 sm:pb-16 sm:pt-10 md:px-8 lg:min-h-[calc(100vh-var(--nav-height))] lg:justify-center lg:px-12 lg:pb-10 lg:pt-8 xl:px-16">
        <div className="grid gap-8 lg:min-h-[min(calc(100svh-var(--nav-height)-2rem),46rem)] lg:items-center xl:grid-cols-[minmax(0,0.98fr)_minmax(24rem,0.92fr)] xl:gap-10">
          <RevealOnScroll className="relative z-10 max-w-2xl">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-app-cyan/20 bg-app-cyan/5 px-3 py-1.5 text-[0.62rem] font-medium uppercase tracking-[0.22em] text-app-cyan">
              <span className="h-1.5 w-1.5 rounded-full bg-app-cyan" />
              Invite-only access
            </div>

            <div className="max-w-[42rem]">
              <h1 className="text-balance font-display text-[2.7rem] font-medium leading-[0.94] tracking-[-0.065em] text-app-text sm:text-[3.35rem] md:text-[4rem] xl:text-[5rem]">
                Grounded{" "}
                <span className="text-app-cyan [text-shadow:var(--hero-title-accent-shadow)]">
                  Synthetic
                </span>{" "}
                Respondent Lab
              </h1>

              <p className="mt-4 max-w-xl text-[0.98rem] leading-7 text-app-muted sm:mt-5 md:text-[1.05rem]">
                Simulate survey responses with realistic AI personas before you
                run live research. Define your audience, product, market, and
                survey, then explore likely insights with confidence.
              </p>
            </div>

            <p className="mt-4 max-w-xl text-[0.92rem] leading-6 text-app-muted/90">
              This workspace is currently available by invitation. Sign in with
              your account, or follow the invite link in your email to get
              started.
            </p>

            <div className="mt-6 flex flex-col gap-3 sm:mt-7 sm:flex-row sm:flex-wrap sm:items-center">
              {readiness.ready ? (
                <Link href="/sign-in" className="w-full sm:w-auto">
                  <Button className="w-full sm:w-auto">
                    Log in
                    <ArrowRightIcon />
                  </Button>
                </Link>
              ) : (
                <Button disabled className="w-full sm:w-auto">
                  Log in
                  <ArrowRightIcon />
                </Button>
              )}
              {readiness.ready ? (
                <Link href="/sign-in" className="w-full sm:w-auto">
                  <Button variant="secondary" className="w-full sm:w-auto">
                    Accept invite
                    <ArrowRightIcon />
                  </Button>
                </Link>
              ) : (
                <Button variant="secondary" disabled className="w-full sm:w-auto">
                  Accept invite
                  <ArrowRightIcon />
                </Button>
              )}
            </div>

            <BackendReadinessNotice
              className="mt-4 max-w-xl"
              readiness={readiness}
            />

            <div className="mt-6 grid max-w-2xl gap-3 md:grid-cols-3">
              <MetricPill
                value="Realistic"
                label="grounded personas"
                accent="gold"
              />
              <MetricPill value="Connected" label="live data" />
              <MetricPill value="Guided" label="step-by-step flow" />
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.08} className="relative z-10">
            <HeroSignalPanel />
          </RevealOnScroll>
        </div>
      </main>
    </div>
  );
}

function PublicTopNav({ backendReady }: { backendReady: boolean }) {
  return (
    <header className="sticky top-0 z-50 border-b [background:var(--nav-bg)] [border-color:var(--nav-border)] backdrop-blur-2xl">
      <div className="mx-auto flex h-[5.5rem] w-full max-w-[92rem] items-center justify-between gap-4 px-4 sm:h-[var(--nav-height)] sm:px-6 lg:px-8">
        <div className="min-w-0 px-1 py-1">
          <div className="truncate font-display text-[clamp(0.66rem,0.86vw,0.92rem)] font-semibold uppercase tracking-[0.08em] text-app-cyan">
            Grounded Synthetic Respondent Lab
          </div>
          <div className="text-[clamp(0.58rem,0.74vw,0.8rem)] tracking-[0.08em] text-app-muted">
            Premium grounded research workflow
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {backendReady ? (
            <>
              <Link
                href="/sign-in"
                className="inline-flex h-10 items-center justify-center rounded-full border px-3.5 text-[0.78rem] font-medium tracking-[0.01em] text-app-text transition [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)] hover:text-app-cyan hover:[background:var(--button-secondary-bg-hover)] sm:px-4 sm:text-[0.82rem]"
              >
                Log in
              </Link>
              <Link
                href="/sign-in"
                className="inline-flex h-10 items-center justify-center rounded-full px-3.5 text-[0.78rem] font-semibold tracking-[0.01em] [background:var(--button-primary-bg)] [color:var(--button-primary-text)] shadow-[var(--button-primary-shadow)] transition hover:-translate-y-0.5 sm:px-4 sm:text-[0.82rem]"
              >
                Accept invite
              </Link>
            </>
          ) : (
            <div className="hidden rounded-full border px-3 py-2 text-[0.72rem] font-medium text-app-muted [background:var(--panel-bg-soft)] [border-color:var(--panel-border)] sm:block">
              Backend waking
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function ArrowRightIcon() {
  return (
    <svg
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14" />
      <path d="m13 5 7 7-7 7" />
    </svg>
  );
}
