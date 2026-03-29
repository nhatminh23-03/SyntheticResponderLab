"use client";

import { motion } from "framer-motion";

import { useSectionRegistry } from "@/providers/section-registry-provider";
import { WorkflowSectionId } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";

type NextSectionArrowProps = {
  targetId: WorkflowSectionId;
  className?: string;
};

export function NextSectionArrow({
  targetId,
  className,
}: NextSectionArrowProps) {
  const { scrollToSection } = useSectionRegistry();

  return (
    <motion.button
      type="button"
      onClick={() => scrollToSection(targetId)}
      className={cn(
        "group absolute bottom-7 left-1/2 z-20 inline-flex h-14 w-14 -translate-x-1/2 items-center justify-center rounded-full border border-app-border bg-white/[0.03] text-app-text backdrop-blur-xl transition hover:border-app-cyan/35 hover:text-app-cyan",
        className
      )}
      animate={{ y: [0, 6, 0] }}
      transition={{ duration: 2.4, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      aria-label="Scroll to next section"
    >
      <svg
        className="h-5 w-5 transition group-hover:translate-y-0.5"
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
  );
}
