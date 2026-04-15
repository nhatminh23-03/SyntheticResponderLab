"use client";

import { motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { MetricPill } from "@/components/ui/metric-pill";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { useStudy } from "@/providers/study-provider";

export function MainHeroSection() {
  const { scrollToSection } = useSectionRegistry();
  const {
    createOrLoadStudy,
    createFreshStudy,
    isCreatingStudy,
    isHydratingStudy,
    studyBootstrapError,
  } = useStudy();

  async function handleStartStudy() {
    const nextStudyId = await createOrLoadStudy();

    if (nextStudyId) {
      scrollToSection("study-mode");
    }
  }

  async function handleStartFreshStudy() {
    const nextStudyId = await createFreshStudy();

    if (nextStudyId) {
      scrollToSection("study-mode");
    }
  }

  return (
    <SectionWrapper
      id="main"
      className="overflow-hidden"
      contentClassName="relative"
    >
      <div className="grid min-h-[calc(100svh-var(--nav-height)-1rem)] items-center gap-8 lg:grid-cols-[minmax(0,0.98fr)_minmax(24rem,0.92fr)] xl:gap-10">
        <RevealOnScroll className="relative z-10 max-w-2xl">
          <div className="max-w-[42rem]">
            <h1 className="text-balance font-display text-[3.2rem] font-medium leading-[0.94] tracking-[-0.07em] text-app-text sm:text-[4rem] xl:text-[5rem]">
              Grounded{" "}
              <span className="text-app-cyan [text-shadow:var(--hero-title-accent-shadow)]">
                Synthetic
              </span>{" "}
              Respondent Lab
            </h1>

            <p className="mt-5 max-w-xl text-base leading-7 text-app-muted md:text-[1.05rem]">
              Build grounded synthetic personas, run AI-powered survey
              simulations, and verify realism with trust signals designed for
              research teams that need confidence, traceability, and calm
              precision.
            </p>
          </div>

          <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button
              onClick={handleStartStudy}
              disabled={isCreatingStudy || isHydratingStudy}
            >
              {isCreatingStudy || isHydratingStudy ? "Preparing Study..." : "Start Study"}
              <ArrowRightIcon />
            </Button>
            <Button
              variant="secondary"
              onClick={() => scrollToSection("study-mode")}
            >
              View Workflow
              <ArrowRightIcon />
            </Button>
          </div>

          <div className="mt-4">
            <button
              type="button"
              onClick={handleStartFreshStudy}
              disabled={isCreatingStudy || isHydratingStudy}
              className="text-sm text-app-muted transition hover:text-app-cyan disabled:cursor-not-allowed disabled:opacity-60"
            >
              Start Fresh Study
            </button>
          </div>

          {studyBootstrapError ? (
            <div className="mt-4 text-sm text-app-gold">
              {studyBootstrapError}
            </div>
          ) : null}

          <div className="mt-6 grid max-w-2xl gap-3 sm:grid-cols-3">
            <MetricPill value="Grounded" label="persona basis" accent="gold" />
            <MetricPill value="Thin Slice" label="api connected" />
            <MetricPill value="Trust-first" label="workflow framing" />
          </div>
        </RevealOnScroll>

        <RevealOnScroll delay={0.08} className="relative z-10">
          <HeroSignalPanel />
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}

function HeroSignalPanel() {
  return (
    <GlassPanel className="mx-auto w-full max-w-[38rem] p-4 sm:p-5">
      <div
        className="relative isolate overflow-hidden rounded-[1.45rem] border px-5 py-5 sm:px-6 sm:py-6"
        style={{
          background: "var(--hero-signal-panel-bg)",
          borderColor: "var(--hero-signal-panel-border)",
        }}
      >
        <div className="section-grid absolute inset-0 opacity-60" />
        <div
          className="absolute left-1/2 top-1/2 h-[17rem] w-[17rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
          style={{ background: "var(--hero-center-glow)" }}
        />
        <div
          className="absolute right-[12%] top-[18%] h-16 w-16 rounded-full blur-2xl"
          style={{ background: "var(--hero-premium-glow)" }}
        />

        <div className="relative z-10 flex min-h-[16rem] items-center justify-center sm:min-h-[18.5rem]">
          <motion.div
            className="absolute h-[16rem] w-[16rem] rounded-full border border-app-cyan/12"
            animate={{ rotate: 360 }}
            transition={{ duration: 36, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
          />
          <motion.div
            className="absolute h-[12rem] w-[12rem] rounded-full border"
            style={{ borderColor: "var(--hero-orbit-border-muted)" }}
            animate={{ rotate: -360 }}
            transition={{ duration: 24, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
          />
          <motion.div
            className="absolute h-[9rem] w-[9rem] rounded-[1.5rem] border border-app-cyan/20"
            style={{
              background: "var(--hero-orbit-core-bg)",
              boxShadow: "var(--hero-orbit-core-shadow)",
            }}
            animate={{ y: [0, -6, 0] }}
            transition={{ duration: 5.6, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
          />
          <motion.div
            className="absolute h-28 w-28 rounded-[1.35rem] backdrop-blur-xl"
            style={{
              background: "var(--hero-core-gradient)",
              boxShadow: "var(--hero-core-shadow)",
            }}
              animate={{ scale: [1, 1.03, 1] }}
              transition={{ duration: 4.5, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
            >
              <div className="flex h-full items-center justify-center">
                <div
                  className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-app-cyan/25"
                  style={{ background: "var(--hero-signal-node-bg)" }}
                >
                  <div className="absolute h-5 w-5 rounded-full bg-app-cyan/65 blur-sm" />
                  <div className="relative h-4 w-4 rounded-full bg-app-cyan" />
                </div>
              </div>
            </motion.div>
          <div
            className="absolute left-[16%] top-[17%] h-2.5 w-2.5 rounded-full bg-app-gold"
            style={{ boxShadow: "var(--hero-dot-gold-shadow)" }}
          />
          <div
            className="absolute right-[18%] top-[34%] h-2 w-2 rounded-full bg-app-cyan"
            style={{ boxShadow: "var(--hero-dot-cyan-shadow)" }}
          />
          <div
            className="absolute bottom-[18%] left-[22%] h-2 w-2 rounded-full bg-white/70"
            style={{ boxShadow: "var(--hero-dot-neutral-shadow)" }}
          />
        </div>

        <div className="relative z-10 mt-2 grid gap-3 sm:grid-cols-2">
          <div
            className="rounded-[1.35rem] border px-5 py-4"
            style={{
              background: "var(--hero-signal-card-bg)",
              borderColor: "var(--hero-signal-card-border)",
              boxShadow: "var(--hero-signal-card-shadow)",
            }}
          >
            <div className="text-[0.64rem] uppercase tracking-[0.24em] text-app-muted/90">
              Persona basis
            </div>
            <div className="mt-2 text-[0.98rem] font-semibold leading-7 text-app-text">
              Demographics, affordability, geography, product, and market context.
            </div>
          </div>
          <div
            className="rounded-[1.35rem] border px-5 py-4"
            style={{
              background: "var(--hero-signal-card-bg)",
              borderColor: "var(--hero-signal-card-border)",
              boxShadow: "var(--hero-signal-card-shadow)",
            }}
          >
            <div className="text-[0.64rem] uppercase tracking-[0.24em] text-app-muted/90">
              Trust posture
            </div>
            <div className="mt-2 text-[0.98rem] font-semibold leading-7 text-app-text">
              Realism framing, validation, stability, and transparency checks.
            </div>
          </div>
        </div>
      </div>
    </GlassPanel>
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
