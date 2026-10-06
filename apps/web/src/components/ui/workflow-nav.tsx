"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { BadgeChip } from "@/components/ui/badge-chip";
import { UserMenuSlot } from "@/components/ui/user-menu-slot";
import { canOpenCompactAppMenu, standaloneAppLinks } from "@/lib/app-navigation";
import { isClassroomStudentPage } from "@/lib/classroom-access";
import { workflowSections, WorkflowSectionId } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";
import { useOptionalSectionRegistry } from "@/providers/section-registry-provider";
import { useTheme } from "@/providers/theme-provider";

const APP_LOGO_SRC = "/brand/app-logo.png";

export function WorkflowNav() {
  const registry = useOptionalSectionRegistry();
  const router = useRouter();
  const pathname = usePathname();
  // /interview and /focus-group are separate routes with no sections of their own, so a tab
  // there is a trip home to that section's anchor instead of a scroll. The ROUTE decides
  // that, not the registry being null: a null on the workflow page means the provider
  // failed to mount, which must stay as loud as the throwing hook used to be.
  const isStandaloneRoute = isClassroomStudentPage(pathname);
  if (!isStandaloneRoute && !registry) {
    throw new Error(
      "WorkflowNav rendered on a workflow route with no SectionRegistryProvider above it."
    );
  }
  const navigationLocked = registry?.navigationLocked ?? false;
  const scrollToSection =
    registry?.scrollToSection ??
    ((id: WorkflowSectionId) => router.push(id === "main" ? "/" : `/#${id}`));
  const { isReady, theme, toggleTheme } = useTheme();
  const [isCompactMenuOpen, setIsCompactMenuOpen] = useState(false);
  const compactMenuDisabled = !canOpenCompactAppMenu(
    navigationLocked,
    standaloneAppLinks.length
  );

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
  // Off the workflow page nothing in the workflow is current, so no tab is highlighted.
  const resolvedActiveSectionId = !registry
    ? null
    : registry.activeSectionId === "main"
    ? "study-mode"
    : registry.activeSectionId;
  const standaloneHere = standaloneAppLinks.find((link) => link.href === pathname);

  const currentIndex = Math.max(
    0,
    navSections.findIndex((section) => {
      const isInterviewGroupTab = section.id === "interview-synthesis";
      return isInterviewGroupTab
        ? resolvedActiveSectionId !== null && interviewGroupIds.has(resolvedActiveSectionId)
        : resolvedActiveSectionId === section.id;
    })
  );

  const currentSection = navSections[currentIndex] ?? navSections[0];
  const progressRatio = navSections.length > 1 ? (currentIndex + 1) / navSections.length : 1;

  const nearbySections = useMemo(
    () => ({
      prev: currentIndex > 0 ? navSections[currentIndex - 1] : null,
      next: currentIndex < navSections.length - 1 ? navSections[currentIndex + 1] : null,
    }),
    [currentIndex, navSections]
  );

  useEffect(() => {
    setIsCompactMenuOpen(false);
  }, [resolvedActiveSectionId]);

  const handleSectionSelect = (sectionId: (typeof navSections)[number]["id"]) => {
    setIsCompactMenuOpen(false);
    window.setTimeout(() => {
      scrollToSection(sectionId);
    }, 220);
  };

  return (
    <>
      <header className="sticky top-[var(--demo-bar-height)] z-50 hidden border-b [background:var(--nav-bg)] [border-color:var(--nav-border)] backdrop-blur-2xl lg:block">
        <div className="mx-auto flex h-[var(--nav-height)] w-full max-w-[92rem] items-center gap-2 px-4 xl:gap-4 xl:px-8">
          <button
            type="button"
            onClick={() => scrollToSection("main", { resetTarget: true })}
            className="flex min-w-0 w-[clamp(10rem,18vw,18rem)] max-w-[18rem] items-center gap-3 px-1 py-1 text-left"
          >
            <AppLogoMark className="h-10 w-10" />
            <div className="min-w-0">
              <div className="font-display text-[clamp(0.66rem,0.86vw,0.92rem)] font-semibold uppercase leading-[1.2] tracking-[0.08em] text-app-cyan">
                Grounded Synthetic Respondent Lab
              </div>
            </div>
          </button>

          <nav className="min-w-0 flex-1 overflow-x-auto fine-scrollbar">
            <div className="flex w-max min-w-full items-center gap-0.5 rounded-[1.5rem] border px-1 py-1.5 [background:var(--theme-panel-inline-gradient)] [border-color:var(--button-secondary-border)] [box-shadow:inset_0_1px_0_rgba(255,255,255,0.03)] xl:px-2">
              {navSections.map((section) => {
                const isInterviewGroupTab = section.id === "interview-synthesis";
                const isActive = isInterviewGroupTab
                  ? resolvedActiveSectionId !== null &&
                    interviewGroupIds.has(resolvedActiveSectionId)
                  : resolvedActiveSectionId === section.id;

                return (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => scrollToSection(section.id, { resetTarget: true })}
                    disabled={navigationLocked}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "relative shrink-0 rounded-full px-[clamp(0.25rem,0.6vw,0.85rem)] py-2 font-medium tracking-[0.003em] transition-all duration-200",
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
                    <span className="relative z-10 block whitespace-nowrap text-[clamp(0.56rem,0.68vw,0.84rem)] leading-none">
                      {section.label}
                    </span>
                  </button>
                );
              })}
              {standaloneAppLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={link.href === pathname ? "page" : undefined}
                  className={cn(
                    "relative shrink-0 rounded-full px-3.5 py-2 font-medium tracking-[0.003em] transition-all duration-200",
                    link.href === pathname
                      ? "border [background:var(--nav-active-pill-bg)] [border-color:var(--button-secondary-border)] text-app-text"
                      : "text-app-muted hover:text-app-text hover:[background:var(--button-secondary-bg-hover)]"
                  )}
                >
                  <span className="block whitespace-nowrap text-[clamp(0.56rem,0.68vw,0.84rem)] leading-none">
                    {link.label}
                  </span>
                </Link>
              ))}
            </div>
          </nav>

          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-app-text transition hover:text-app-cyan [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)]"
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

          <UserMenuSlot />
        </div>
      </header>

      {/* Sized by its content, not --nav-height; AppShell measures it (data-compact-menu-bar) into --nav-height. */}
      <header
        data-compact-menu-bar
        className="sticky top-[var(--demo-bar-height)] z-50 border-b [background:var(--nav-bg)] [border-color:var(--nav-border)] backdrop-blur-2xl lg:hidden"
      >
        <div className="mx-auto max-w-[92rem] px-3 pb-2 pt-3 sm:px-4">
          <div className="flex items-start justify-between gap-3">
            <button
              type="button"
              onClick={() => scrollToSection("main", { resetTarget: true })}
              className="flex min-w-0 flex-1 items-center gap-2.5 px-0 py-0 text-left"
            >
              <AppLogoMark className="h-9 w-9" />
              <div className="min-w-0">
                <div className="truncate font-display text-[0.76rem] font-semibold uppercase tracking-[0.08em] text-app-cyan sm:text-[0.82rem]">
                  Grounded Synthetic Respondent Lab
                </div>
                <div className="mt-1 truncate text-[0.6rem] tracking-[0.08em] text-app-muted sm:text-[0.66rem]">
                  Premium grounded research workflow
                </div>
              </div>
            </button>

            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={toggleTheme}
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-app-text transition hover:text-app-cyan [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)]"
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

              <UserMenuSlot />
            </div>
          </div>

          <div className="relative mt-3 rounded-[1.2rem] border px-3 py-3 shadow-[0_12px_28px_rgba(0,0,0,0.12)] [background:var(--glass-panel-bg)] [border-color:var(--button-secondary-border)]">
            <div className="flex items-center gap-3">
              {/* Standalone destinations must remain reachable while workflow steps are locked. */}
              <button
                type="button"
                onClick={() => setIsCompactMenuOpen((current) => !current)}
                disabled={compactMenuDisabled}
                className={cn(
                  "inline-flex min-w-0 flex-1 items-center justify-between rounded-[1.05rem] border px-3 py-2.5 text-left transition",
                  "[background:var(--nav-active-pill-bg)] [border-color:var(--button-secondary-border)]",
                  compactMenuDisabled && "cursor-not-allowed opacity-60"
                )}
                aria-expanded={isCompactMenuOpen}
                aria-controls="compact-workflow-menu"
                >
                  <span className="min-w-0">
                    <span className="block text-[0.62rem] uppercase tracking-[0.22em] text-app-muted">
                      Current Step
                    </span>
                    <span className="mt-1 block truncate text-[0.95rem] font-medium text-app-text sm:text-[1rem]">
                      {standaloneHere?.label ?? currentSection?.label ?? "Set Up"}
                    </span>
                  </span>
                  <span
                    className={cn(
                    "ml-3 shrink-0 text-app-cyan transition-transform duration-200",
                    isCompactMenuOpen && "rotate-180"
                  )}
                >
                  <ChevronDownGlyph />
                </span>
              </button>

              {registry ? (
                <div className="shrink-0 rounded-[1.05rem] border px-3 py-2 text-right [background:var(--status-neutral-bg)] [border-color:var(--button-secondary-border)]">
                  <div className="text-[0.6rem] uppercase tracking-[0.18em] text-app-muted">Progress</div>
                  <div className="mt-1 text-[0.92rem] font-medium text-app-text">
                    {currentIndex + 1} of {navSections.length}
                  </div>
                </div>
              ) : null}
            </div>

            {registry ? (
              <>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full border [background:var(--status-neutral-bg)] [border-color:var(--button-secondary-border)]">
                  <motion.div
                    animate={{ width: `${Math.max(progressRatio * 100, 8)}%` }}
                    transition={{ duration: 0.3, ease: "easeOut" }}
                    className="h-full rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.9),rgba(216,186,103,0.72))]"
                  />
                </div>

                <div className="mt-3 flex items-center justify-between gap-3 text-[0.72rem] text-app-muted">
                  <span className="min-w-0 truncate">
                    {nearbySections.prev ? `Prev: ${nearbySections.prev.label}` : "Start"}
                  </span>
                  <span className="min-w-0 truncate text-right">
                    {nearbySections.next ? `Next: ${nearbySections.next.label}` : "Final step"}
                  </span>
                </div>
              </>
            ) : null}

            <AnimatePresence initial={false}>
              {isCompactMenuOpen ? (
                <motion.div
                  id="compact-workflow-menu"
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  className="absolute inset-x-0 top-full z-30 mt-2 overflow-hidden rounded-[1.15rem] border p-3 shadow-[0_18px_44px_rgba(0,0,0,0.22)] [background:var(--color-background)] [border-color:var(--button-secondary-border)]"
                >
                  <div className="fine-scrollbar max-h-[min(calc(100svh-var(--top-chrome)-1.25rem),28rem)] space-y-2 overflow-y-auto pr-1">
                    {navSections.map((section, index) => {
                      const isInterviewGroupTab = section.id === "interview-synthesis";
                      const isActive = isInterviewGroupTab
                        ? resolvedActiveSectionId !== null &&
                          interviewGroupIds.has(resolvedActiveSectionId)
                        : resolvedActiveSectionId === section.id;
                      const isCompleted = index < currentIndex;

                      return (
                        <button
                          key={section.id}
                          type="button"
                          onClick={() => handleSectionSelect(section.id)}
                          disabled={navigationLocked}
                          className={cn(
                            "flex w-full items-center justify-between gap-3 rounded-[1rem] border px-3.5 py-2.5 text-left transition",
                            navigationLocked && "cursor-not-allowed opacity-60",
                            isActive
                              ? "[background:var(--nav-active-pill-bg)] [border-color:var(--button-secondary-border)]"
                              : "[background:var(--theme-panel-inline-gradient)] [border-color:var(--button-secondary-border)]"
                          )}
                        >
                          <div className="flex min-w-0 items-center gap-3">
                            <div
                              className={cn(
                                "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[0.68rem] font-medium",
                                isActive
                                  ? "border-app-cyan/30 bg-app-cyan/12 text-app-cyan"
                                  : isCompleted
                                  ? "border-app-gold/30 bg-app-gold/12 text-app-gold"
                                  : "border-app-border bg-white/0 text-app-muted"
                              )}
                            >
                              {isCompleted ? <CheckGlyph /> : index + 1}
                            </div>
                            <div className="min-w-0">
                              <div className="truncate text-[0.92rem] font-medium text-app-text">
                                {section.label}
                              </div>
                              <div className="mt-1 text-[0.66rem] uppercase tracking-[0.18em] text-app-muted">
                                {isActive ? "Current" : isCompleted ? "Completed" : "Upcoming"}
                              </div>
                            </div>
                          </div>

                          {isActive ? <BadgeChip tone="cyan">Here</BadgeChip> : null}
                        </button>
                      );
                    })}
                    {standaloneAppLinks.map((link) => (
                      <Link
                        key={link.href}
                        href={link.href}
                        onClick={() => setIsCompactMenuOpen(false)}
                        aria-current={link.href === pathname ? "page" : undefined}
                        className={cn(
                          "flex w-full items-center justify-between gap-3 rounded-[1rem] border px-3.5 py-2.5 text-left transition [border-color:var(--button-secondary-border)]",
                          link.href === pathname
                            ? "[background:var(--nav-active-pill-bg)]"
                            : "[background:var(--theme-panel-inline-gradient)]"
                        )}
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <div className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-app-cyan/30 bg-app-cyan/12 text-app-cyan">
                            <InterviewGlyph />
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-[0.92rem] font-medium text-app-text">
                              {link.label}
                            </div>
                            <div className="mt-1 text-[0.66rem] uppercase tracking-[0.18em] text-app-muted">
                              {link.href === pathname ? "Current" : "Standalone section"}
                            </div>
                          </div>
                        </div>
                      </Link>
                    ))}
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        </div>
      </header>
    </>
  );
}

function InterviewGlyph() {
  return (
    <svg
      className="h-3.5 w-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M7 8h10" />
      <path d="M7 12h6" />
      <path d="M5 19l-1 3 4-2h9a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3H7a3 3 0 0 0-3 3v10a3 3 0 0 0 1 2Z" />
    </svg>
  );
}

export function AppLogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)]",
        className
      )}
      aria-hidden="true"
    >
      <img
        src={APP_LOGO_SRC}
        alt=""
        className="h-full w-full scale-[1.24] object-cover"
      />
    </span>
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

function ChevronDownGlyph() {
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
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function CheckGlyph() {
  return (
    <svg
      className="h-3.5 w-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m5 12 4.2 4.2L19 7.5" />
    </svg>
  );
}
