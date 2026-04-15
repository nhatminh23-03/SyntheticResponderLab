"use client";

import { motion } from "framer-motion";

import { workflowSections } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { useTheme } from "@/providers/theme-provider";

export function WorkflowNav() {
  const { activeSectionId, navigationLocked, scrollToSection } = useSectionRegistry();
  const { isReady, theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-50 border-b [background:var(--nav-bg)] [border-color:var(--nav-border)] backdrop-blur-2xl">
      <div className="mx-auto flex h-[var(--nav-height)] w-full max-w-[92rem] items-center gap-4 px-4 md:px-6 lg:px-10">
        <button
          type="button"
          onClick={() => scrollToSection("main")}
          className="flex min-w-[14rem] shrink-0 items-center text-left sm:min-w-[18rem] xl:min-w-[22rem]"
        >
          <div className="min-w-0">
            <div className="font-display text-[0.74rem] font-semibold uppercase tracking-[0.12em] text-app-cyan sm:text-[0.8rem] xl:text-[0.84rem]">
              <span className="sm:hidden">Grounded Synthetic Lab</span>
              <span className="hidden sm:inline">Grounded Synthetic Respondent Lab</span>
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
                    ? "text-app-text [background:var(--nav-active-pill-bg)]"
                    : "text-app-muted hover:text-app-cyan"
                )}
              >
                {section.label}
                {isActive ? (
                  <motion.span
                    layoutId="workflow-nav-indicator"
                    className="absolute inset-x-3 bottom-0 h-px bg-app-cyan shadow-[var(--nav-indicator-shadow)]"
                  />
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex items-center gap-2 rounded-full border px-3 py-2 text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-app-text transition hover:text-app-cyan [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)]"
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
            <span className="hidden sm:inline">{isReady ? theme : "Theme"}</span>
          </button>

          <button
            type="button"
            disabled
            className="hidden rounded-full border px-4 py-1.5 text-[0.62rem] uppercase tracking-[0.22em] [border-color:var(--nav-premium-chip-border)] [background:var(--nav-premium-chip-bg)] [color:var(--chip-gold-text)] [box-shadow:var(--nav-premium-chip-shadow)] xl:flex"
            title="Interview extension is not implemented yet."
          >
            Interview
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
