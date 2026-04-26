"use client";

import { motion } from "framer-motion";

import { useSectionRegistry } from "@/providers/section-registry-provider";

export function ChapterNextArrow() {
  const {
    activeSectionId,
    canAdvanceWithinSection,
    goActiveSectionDown,
    goNextSection,
    hasNextSection,
    navigationLocked,
  } = useSectionRegistry();

  const useInSectionAdvance =
    (activeSectionId === "analysis" || activeSectionId === "insights") &&
    canAdvanceWithinSection(activeSectionId);

  if ((!hasNextSection && !useInSectionAdvance) || navigationLocked) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[max(0.9rem,env(safe-area-inset-bottom))] z-40 flex justify-center px-4 sm:bottom-[max(1.1rem,env(safe-area-inset-bottom))] sm:px-6 lg:bottom-5">
      <motion.button
        type="button"
        onClick={useInSectionAdvance ? goActiveSectionDown : goNextSection}
        className="pointer-events-auto group relative inline-flex h-12 w-12 items-center justify-center rounded-full border border-app-cyan/25 text-app-text shadow-[var(--floating-control-shadow)] backdrop-blur-xl transition hover:border-app-cyan/45 hover:text-app-cyan [background:var(--floating-control-bg)] sm:h-[3.6rem] sm:w-[3.6rem] lg:h-[4.35rem] lg:w-[4.35rem]"
        animate={{ y: [0, 8, 0] }}
        transition={{
          duration: 2.4,
          repeat: Number.POSITIVE_INFINITY,
          ease: "easeInOut",
        }}
        aria-label={useInSectionAdvance ? "Continue through this section" : "Go to the next section"}
      >
        <span className="absolute inset-0 rounded-full blur-xl transition opacity-80 group-hover:opacity-100 [background:var(--color-brand-primary-soft)]" />
        <span className="absolute -top-7 hidden rounded-full border border-app-cyan/20 px-2.5 py-1 text-[0.58rem] uppercase tracking-[0.22em] text-app-cyan shadow-[var(--floating-control-label-shadow)] [background:var(--floating-control-label-bg)] sm:inline-flex lg:-top-8 lg:px-3 lg:text-[0.62rem] lg:tracking-[0.26em]">
          {useInSectionAdvance ? "More" : "Next"}
        </span>
        <svg
          className="relative h-4 w-4 transition group-hover:translate-y-0.5 sm:h-[1.1rem] sm:w-[1.1rem] lg:h-5 lg:w-5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 5v14" />
          <path d="m6 13 6 6 6-6" />
        </svg>
      </motion.button>
    </div>
  );
}
