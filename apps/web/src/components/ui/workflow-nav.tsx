"use client";

import { motion } from "framer-motion";

import { workflowSections } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { useTheme } from "@/providers/theme-provider";

export function WorkflowNav() {
  const { activeSectionId, navigationLocked, scrollToSection } = useSectionRegistry();
  const { isReady, theme, toggleTheme } = useTheme();
  const navSections = workflowSections.filter(
    (section) =>
      section.id !== "main" &&
      section.id !== "research-brief" &&
      section.id !== "interview-insights"
  );

  const interviewGroupIds = new Set([
    "interview-synthesis",
    "research-brief",
    "interview-insights",
  ]);
  const resolvedActiveSectionId =
    activeSectionId === "main" ? "study-mode" : activeSectionId;

  return (
    <header className="sticky top-0 z-50 border-b [background:var(--nav-bg)] [border-color:var(--nav-border)] backdrop-blur-2xl">
      <div className="mx-auto flex h-[var(--nav-height)] w-full max-w-[92rem] items-center gap-3 px-3 md:gap-4 md:px-5 lg:px-8">
        <button
          type="button"
          onClick={() => scrollToSection("main")}
          className="flex w-[clamp(18rem,33vw,30rem)] shrink-0 items-center rounded-[1.2rem] px-2 py-1.5 text-left transition-colors hover:[background:var(--button-secondary-bg)]"
        >
          <div className="min-w-0">
            <div className="font-display whitespace-nowrap text-[clamp(0.66rem,0.86vw,0.92rem)] font-semibold uppercase tracking-[0.095em] text-app-cyan">
              Grounded Synthethic Respondent Lab
            </div>
            <div className="whitespace-nowrap text-[clamp(0.58rem,0.74vw,0.8rem)] tracking-[0.09em] text-app-muted">
              Preminum Grounded Research Workflow
            </div>
          </div>
        </button>

        <nav className="min-w-0 flex-1 overflow-x-auto">
          <div className="inline-flex w-max items-center rounded-[1.5rem] border px-2 py-1.5 [background:var(--theme-panel-inline-gradient)] [border-color:var(--button-secondary-border)] [box-shadow:inset_0_1px_0_rgba(255,255,255,0.03)]">
            {navSections.map((section) => {
              const isInterviewGroupTab = section.id === "interview-synthesis";
              const isActive = isInterviewGroupTab
                ? interviewGroupIds.has(resolvedActiveSectionId)
                : resolvedActiveSectionId === section.id;

              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => scrollToSection(section.id)}
                  disabled={navigationLocked}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "relative shrink-0 rounded-full px-3 py-2 font-medium tracking-[0.003em] transition-all duration-200",
                    "text-center",
                    navigationLocked && "cursor-not-allowed opacity-55",
                    isActive
                      ? "text-app-text"
                      : "text-app-muted hover:text-app-text hover:[background:var(--button-secondary-bg-hover)]"
                  )}
                >
                  {isActive ? (
                    <motion.span
                      layoutId="workflow-nav-pill"
                      className="absolute inset-0 rounded-full border [background:var(--nav-active-pill-bg)] [border-color:var(--button-secondary-border)] shadow-[0_0_0_1px_rgba(255,255,255,0.02),0_14px_28px_rgba(15,216,255,0.08)]"
                    />
                  ) : null}
                  <span className="relative z-10 block whitespace-nowrap text-[clamp(0.68rem,0.82vw,0.98rem)] leading-none">
                    {section.label}
                  </span>
                </button>
              );
            })}
          </div>
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border text-app-text transition hover:text-app-cyan [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)]"
            aria-label={
              isReady
                ? `Switch to ${theme === "dark" ? "light" : "dark"} mode`
                : "Toggle color theme"
            }
            title={
              isReady
                ? `Switch to ${theme === "dark" ? "light" : "dark"} mode`
                : "Toggle color theme"
            }
          >
            <ThemeGlyph theme={theme} />
          </button>
        </div>
      </div>
    </header>
  );
}

function ThemeGlyph({ theme }: { theme: "dark" | "light" }) {
  if (theme === "light") {
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
        <circle cx="12" cy="12" r="4.5" />
        <path d="M12 2.75v2.2" />
        <path d="M12 19.05v2.2" />
        <path d="m4.93 4.93 1.56 1.56" />
        <path d="m17.51 17.51 1.56 1.56" />
        <path d="M2.75 12h2.2" />
        <path d="M19.05 12h2.2" />
        <path d="m4.93 19.07 1.56-1.56" />
        <path d="m17.51 6.49 1.56-1.56" />
      </svg>
    );
  }

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
      <path d="M21 12.8A8.8 8.8 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8Z" />
    </svg>
  );
}
