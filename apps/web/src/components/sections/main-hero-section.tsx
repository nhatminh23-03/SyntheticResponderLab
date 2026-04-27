"use client";

import { Button } from "@/components/ui/button";
import { MetricPill } from "@/components/ui/metric-pill";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import { HeroSignalPanel } from "@/components/sections/hero-signal-panel";
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
      contentClassName="relative lg:justify-center"
    >
      <div className="grid gap-8 lg:min-h-[min(calc(100svh-var(--nav-height)-2rem),46rem)] lg:items-center xl:grid-cols-[minmax(0,0.98fr)_minmax(24rem,0.92fr)] xl:gap-10">
        <RevealOnScroll className="relative z-10 max-w-2xl">
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

          <div className="mt-6 flex flex-col gap-3 sm:mt-7 sm:flex-row sm:flex-wrap sm:items-center">
            <Button
              onClick={handleStartStudy}
              disabled={isCreatingStudy || isHydratingStudy}
              className="w-full sm:w-auto"
            >
              {isCreatingStudy || isHydratingStudy ? "Preparing Setup..." : "Start Setup"}
              <ArrowRightIcon />
            </Button>
            <Button
              variant="secondary"
              onClick={() => scrollToSection("study-mode")}
              className="w-full sm:w-auto"
            >
              See Workflow
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
              Start New Study
            </button>
          </div>

          {studyBootstrapError ? (
            <div className="mt-4 text-sm text-app-gold">
              {studyBootstrapError}
            </div>
          ) : null}

          <div className="mt-6 grid max-w-2xl gap-3 md:grid-cols-3">
            <MetricPill value="Realistic" label="grounded personas" accent="gold" />
            <MetricPill value="Connected" label="live data" />
            <MetricPill value="Guided" label="step-by-step flow" />
          </div>
        </RevealOnScroll>

        <RevealOnScroll delay={0.08} className="relative z-10">
          <HeroSignalPanel />
        </RevealOnScroll>
      </div>
    </SectionWrapper>
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
