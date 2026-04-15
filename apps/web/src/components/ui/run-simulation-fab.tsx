"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";

import { isReadyToRun } from "@/lib/study-utils";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";

export function RunSimulationFab() {
  const { study } = useStudy();
  const { scrollToSection, navigationLocked } = useSectionRegistry();

  const isReady = useMemo(() => isReadyToRun(study), [study]);
  const canClick = isReady && !navigationLocked;

  return (
    <motion.button
      type="button"
      disabled={!canClick}
      onClick={canClick ? () => scrollToSection("run-simulation") : undefined}
      title={!isReady ? "Save Audience, Survey, and Experiment to unlock" : undefined}
      animate={
        isReady
          ? {
              boxShadow: [
                "0 0 42px rgba(15,216,255,0.18)",
                "0 0 56px rgba(15,216,255,0.28)",
                "0 0 42px rgba(15,216,255,0.18)",
              ],
            }
          : {}
      }
      transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      className={cn(
        "pointer-events-auto inline-flex items-center gap-2 rounded-full px-5 py-2.5",
        "text-sm font-semibold tracking-[0.03em] backdrop-blur-xl",
        "transition duration-300",
        canClick
          ? "border border-app-cyan/40 bg-[linear-gradient(135deg,rgba(118,228,255,0.18),rgba(15,216,255,0.10))] text-app-text shadow-glow hover:-translate-y-0.5 hover:shadow-[0_0_50px_rgba(15,216,255,0.26)]"
          : "cursor-not-allowed opacity-60 border border-white/[0.08] bg-[rgba(17,24,29,0.88)] text-app-muted"
      )}
    >
      <span aria-hidden>▶</span>
      <span>Run Simulation</span>
    </motion.button>
  );
}
