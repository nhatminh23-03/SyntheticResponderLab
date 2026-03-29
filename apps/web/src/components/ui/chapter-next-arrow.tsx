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
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-40 flex justify-center px-6">
      <motion.button
        type="button"
        onClick={useInSectionAdvance ? goActiveSectionDown : goNextSection}
        className="pointer-events-auto group relative inline-flex h-[4.35rem] w-[4.35rem] items-center justify-center rounded-full border border-app-cyan/30 bg-[radial-gradient(circle_at_30%_30%,rgba(15,216,255,0.24),rgba(17,24,29,0.92)_68%)] text-app-text shadow-[0_0_0_1px_rgba(15,216,255,0.12),0_0_28px_rgba(15,216,255,0.16),0_18px_42px_rgba(0,0,0,0.4)] backdrop-blur-xl transition hover:border-app-cyan/45 hover:text-app-cyan"
        animate={{ y: [0, 8, 0], boxShadow: [
          "0 0 0 1px rgba(15,216,255,0.12), 0 0 28px rgba(15,216,255,0.16), 0 18px 42px rgba(0,0,0,0.4)",
          "0 0 0 1px rgba(15,216,255,0.2), 0 0 36px rgba(15,216,255,0.24), 0 20px 44px rgba(0,0,0,0.42)",
          "0 0 0 1px rgba(15,216,255,0.12), 0 0 28px rgba(15,216,255,0.16), 0 18px 42px rgba(0,0,0,0.4)"
        ] }}
        transition={{
          duration: 2.4,
          repeat: Number.POSITIVE_INFINITY,
          ease: "easeInOut",
        }}
        aria-label={useInSectionAdvance ? "Continue through this section" : "Go to the next section"}
      >
        <span className="absolute inset-0 rounded-full bg-app-cyan/10 blur-xl transition group-hover:bg-app-cyan/15" />
        <span className="absolute -top-8 rounded-full border border-app-cyan/20 bg-[rgba(10,14,18,0.84)] px-3 py-1 text-[0.62rem] uppercase tracking-[0.26em] text-app-cyan shadow-[0_10px_24px_rgba(0,0,0,0.28)]">
          {useInSectionAdvance ? "More" : "Next"}
        </span>
        <svg
          className="relative h-5 w-5 transition group-hover:translate-y-0.5"
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
