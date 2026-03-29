"use client";

import { motion } from "framer-motion";

import { workflowSections } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";
import { useSectionRegistry } from "@/providers/section-registry-provider";

export function WorkflowNav() {
  const { activeSectionId, navigationLocked, scrollToSection } = useSectionRegistry();

  return (
    <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-[rgba(10,15,19,0.78)] backdrop-blur-2xl">
      <div className="mx-auto flex h-[var(--nav-height)] w-full max-w-[92rem] items-center gap-4 px-4 md:px-6 lg:px-10">
        <button
          type="button"
          onClick={() => scrollToSection("main")}
          className="flex min-w-0 shrink-0 items-center gap-3 text-left"
        >
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(216,186,103,0.12)] font-display text-sm font-extrabold tracking-[0.18em] text-app-gold">
            GL
          </span>
          <div className="min-w-0 max-w-[13rem] md:max-w-[16rem] xl:max-w-[20rem]">
            <div className="truncate font-display text-xs font-semibold uppercase tracking-[0.18em] text-app-cyan md:text-sm">
              Grounded Synthetic Respondent Lab
            </div>
            <div className="hidden text-[0.68rem] tracking-[0.16em] text-app-muted lg:block">
              Premium grounded research workflow
            </div>
          </div>
        </button>

        <nav className="fine-scrollbar flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {workflowSections.map((section) => {
            const isActive = activeSectionId === section.id;

            return (
              <button
                key={section.id}
                type="button"
                onClick={() => scrollToSection(section.id)}
                disabled={navigationLocked}
                className={cn(
                  "relative shrink-0 rounded-full px-3 py-2 text-sm tracking-[0.01em] transition-colors",
                  navigationLocked && "cursor-not-allowed opacity-55",
                  isActive
                    ? "text-app-text"
                    : "text-app-muted hover:text-app-cyan"
                )}
              >
                {section.label}
                {isActive ? (
                  <motion.span
                    layoutId="workflow-nav-indicator"
                    className="absolute inset-x-3 bottom-0 h-px bg-app-cyan shadow-[0_0_18px_rgba(15,216,255,0.42)]"
                  />
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="hidden shrink-0 items-center gap-2 xl:flex">
          <button
            type="button"
            disabled
            className="rounded-full border border-app-gold/30 bg-[rgba(216,186,103,0.14)] px-4 py-1.5 text-[0.62rem] uppercase tracking-[0.22em] text-app-gold shadow-[0_0_24px_rgba(216,186,103,0.12)]"
            title="Interview extension is not implemented yet."
          >
            Interview
          </button>
        </div>
      </div>
    </header>
  );
}
