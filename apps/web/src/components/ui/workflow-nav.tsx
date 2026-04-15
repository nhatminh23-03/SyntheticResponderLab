"use client";

import { motion } from "framer-motion";

import { workflowSections } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { useTheme } from "@/providers/theme-provider";

export function WorkflowNav() {
  const { activeSectionId, navigationLocked, scrollToSection } = useSectionRegistry();
  const { isReady, theme, toggleTheme } = useTheme();
  const navSections = workflowSections;

  return (
    <header className="sticky top-0 z-50 border-b [background:var(--nav-bg)] [border-color:var(--nav-border)] backdrop-blur-2xl">
      <div className="mx-auto flex h-[var(--nav-height)] w-full max-w-[92rem] items-center gap-3 px-3 md:px-5 lg:px-8">
        <button
          type="button"
          onClick={() => scrollToSection("main")}
          className="flex w-[clamp(6.75rem,13vw,12rem)] shrink-0 items-center text-left"
        >
          <div className="min-w-0">
            <div className="font-display text-[clamp(0.58rem,0.92vw,0.84rem)] font-semibold uppercase tracking-[0.12em] text-app-cyan">
              <span className="sm:hidden">Grounded Synthetic Lab</span>
              <span className="hidden sm:inline">Grounded Synthetic Respondent Lab</span>
            </div>
            <div className="hidden text-[0.62rem] tracking-[0.14em] text-app-muted 2xl:block">
              Premium grounded research workflow
            </div>
          </div>
        </button>

        <nav className="min-w-0 flex-1 overflow-hidden">
          <div
            className="grid w-full items-center gap-[clamp(0.02rem,0.12vw,0.12rem)]"
            style={{
              gridTemplateColumns: `repeat(${navSections.length}, minmax(0, 1fr))`,
            }}
          >
            {navSections.map((section) => {
              const isActive = activeSectionId === section.id;
              const isTwoLineLabel =
                section.id === "research-brief" ||
                section.id === "interview-insights";

              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => scrollToSection(section.id)}
                  disabled={navigationLocked}
                  className={cn(
                    "relative min-w-0 rounded-full px-[clamp(0.04rem,0.24vw,0.24rem)] py-[0.34rem] font-medium tracking-[0.005em] transition-colors",
                    "text-center",
                    navigationLocked && "cursor-not-allowed opacity-55",
                    isActive
                      ? "text-app-text"
                      : "text-app-muted hover:text-app-cyan"
                  )}
                >
                  <span
                    className={cn(
                      "block",
                      isTwoLineLabel
                        ? "mx-auto max-w-[9ch] whitespace-normal break-words text-[clamp(0.64rem,0.92vw,1.06rem)] leading-[1.05]"
                        : "whitespace-nowrap text-[clamp(0.58rem,0.8vw,0.96rem)] leading-none"
                    )}
                    style={
                      isTwoLineLabel
                        ? {
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }
                        : undefined
                    }
                  >
                    {section.label}
                  </span>
                  {isActive ? (
                    <motion.span
                      layoutId="workflow-nav-indicator"
                      className="absolute bottom-0 h-px bg-app-cyan shadow-[var(--nav-indicator-shadow)]"
                      style={{ left: "clamp(0.06rem, 0.26vw, 0.26rem)", right: "clamp(0.06rem, 0.26vw, 0.26rem)" }}
                    />
                  ) : null}
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
