"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { loadNeoSurveyPreset, saveStudyMode } from "@/lib/api";
import { buildStudyModeStatusMessage, StudyModeValue } from "@/lib/setup-flow-utils";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";

const studyModeCards: Array<{
  value: StudyModeValue;
  eyebrow: string;
  title: string;
  description: string;
  bullets: string[];
  accent: "cyan" | "gold";
}> = [
  {
    value: "neo_smart",
    eyebrow: "Guided Demo",
    title: "Neo Smart Living Demo",
    description:
      "Use the Neo Smart framing, sharper defaults, and more curated context for the premium guided demo experience.",
    bullets: [
      "Pre-framed around the Neo Smart Living story",
      "Best for a polished walkthrough",
      "Trust framing stays close to the demo narrative",
    ],
    accent: "gold",
  },
  {
    value: "general",
    eyebrow: "Flexible Mode",
    title: "General Custom Study",
    description:
      "Start from a cleaner open canvas for custom research projects, broader use cases, and reusable workflow setup.",
    bullets: [
      "Neutral setup path for general research",
      "Best for reusable studies beyond the demo brand",
      "Keeps the same grounded trust-first engine",
    ],
    accent: "cyan",
  },
];

export function StudyModeSection() {
  const {
    studyId,
    study,
    createOrLoadStudy,
    createFreshStudy,
    isCreatingStudy,
    isHydratingStudy,
    refreshStudy,
  } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [selectedMode, setSelectedMode] = useState<StudyModeValue | null>(null);
  const [isSavingMode, setIsSavingMode] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function hydrateStudyMode() {
      if (!studyId || !study) {
        if (!cancelled) {
          setSelectedMode(null);
          setStatusMessage(null);
        }
        return;
      }

      const nextValue = study.study_mode.value;

      if (
        !cancelled &&
        (nextValue === "neo_smart" || nextValue === "general")
      ) {
        setSelectedMode(nextValue);
        setStatusMessage(
          nextValue === "neo_smart"
            ? "Current mode: Neo Smart Living Demo"
            : "Current mode: General Custom Study"
        );
      } else if (!cancelled) {
        setSelectedMode(null);
        setStatusMessage(null);
      }
    }

    void hydrateStudyMode();

    return () => {
      cancelled = true;
    };
  }, [studyId, study?.study_mode?.updated_at, study?.study_mode?.value]);

  async function handleSelectMode(nextMode: StudyModeValue) {
    setErrorMessage(null);
    setStatusMessage(null);
    setIsSavingMode(true);

    try {
      const currentMode =
        study?.study_mode?.value === "neo_smart" || study?.study_mode?.value === "general"
          ? study.study_mode.value
          : null;
      const isSwitchingModes = currentMode !== null && currentMode !== nextMode;
      const resolvedStudyId = isSwitchingModes
        ? await createFreshStudy()
        : (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await saveStudyMode(resolvedStudyId, nextMode);
      setSelectedMode(result.value as StudyModeValue);
      const shouldAutoLoadNeoSurvey =
        nextMode === "neo_smart" &&
        (isSwitchingModes || study?.survey?.status !== "saved");
      let neoSurveyPresetWarning: string | null = null;

      if (shouldAutoLoadNeoSurvey) {
        try {
          await loadNeoSurveyPreset(resolvedStudyId);
        } catch (error) {
          neoSurveyPresetWarning =
            error instanceof Error
              ? error.message
              : "The Neo survey preset could not be loaded automatically.";
        }
      }

      const refreshedStudy = await refreshStudy(resolvedStudyId);
      const preservedSavedSections = [
        refreshedStudy?.audience?.status === "saved" ? "Audience" : null,
        refreshedStudy?.product?.status === "saved" ? "Product" : null,
        refreshedStudy?.market?.status === "saved" ? "Market" : null,
        refreshedStudy?.survey?.status === "saved" ? "Survey" : null,
        refreshedStudy?.experiment?.status === "saved" ? "Experiment" : null,
      ].filter(Boolean) as string[];
      const baseMessage = buildStudyModeStatusMessage(
        nextMode,
        isSwitchingModes ? [] : preservedSavedSections
      );
      const workspaceMessage = isSwitchingModes
        ? " A fresh study workspace was created for the new mode so the downstream setup starts clean."
        : "";
      const neoSurveyMessage =
        nextMode === "neo_smart"
          ? shouldAutoLoadNeoSurvey
            ? neoSurveyPresetWarning
              ? ` Neo mode is saved, but the bundled survey preset still needs manual attention: ${neoSurveyPresetWarning}`
              : " The bundled Neo survey preset was loaded automatically."
            : " Neo defaults remain available across the guided setup path."
          : " Downstream setup sections now start empty until you fill and save them.";
      setStatusMessage(`${baseMessage}${workspaceMessage}${neoSurveyMessage}`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to save the study mode right now."
      );
    } finally {
      setIsSavingMode(false);
    }
  }

  const isBusy = isCreatingStudy || isHydratingStudy || isSavingMode;

  return (
    <SectionWrapper
      id="study-mode"
      className="overflow-hidden"
      contentClassName="relative"
    >
      <div className="grid min-h-[calc(100svh-var(--nav-height)-1rem)] gap-8 lg:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)] lg:items-center">
        <RevealOnScroll>
          <SectionHeader
            index={1}
            eyebrow="Study Setup"
            title="Choose the mode that shapes the rest of the workflow."
            description="This is the next chapter after the hero: decide whether this study should follow the curated Neo Smart demo path or a more flexible general research path, then carry that decision through the one-page setup flow."
          />

          <div className="mt-6 space-y-4">
            <div className="flex flex-wrap gap-3">
              <BadgeChip tone="gold">Step 01 of 06</BadgeChip>
              <BadgeChip tone="cyan">Backend save enabled</BadgeChip>
            </div>

            

            <div className="min-h-10 text-sm">
              {errorMessage ? (
                <span className="text-app-gold">{errorMessage}</span>
              ) : statusMessage ? (
                <span className="text-app-cyan">{statusMessage}</span>
              ) : (
                <span className="text-app-muted">
                  Pick a mode to decide whether the next sections should start guided or blank.
                </span>
              )}
            </div>

            <Button
              variant="secondary"
              onClick={() => scrollToSection("audience")}
              disabled={!selectedMode}
            >
              Continue to Audience
              <ArrowRightIcon />
            </Button>
          </div>
        </RevealOnScroll>

        <div className="grid gap-4 lg:grid-cols-2">
          {studyModeCards.map((card, index) => {
            const isSelected = selectedMode === card.value;

            return (
              <RevealOnScroll key={card.value} delay={0.05 + index * 0.08}>
                <motion.button
                  type="button"
                  onClick={() => handleSelectMode(card.value)}
                  whileHover={{ y: -3 }}
                  transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
                  className="w-full text-left"
                  disabled={isBusy}
                >
                  <GlassPanel
                    className={cn(
                      "h-full p-4 transition duration-300 sm:p-5",
                      isSelected
                        ? "border-app-cyan/30 bg-[linear-gradient(180deg,rgba(118,228,255,0.12),rgba(255,255,255,0.04))] shadow-[0_0_60px_rgba(15,216,255,0.12)]"
                        : "hover:border-white/15 hover:bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02))]"
                    )}
                  >
                    <div className="flex h-full flex-col rounded-[1.45rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.82),rgba(12,18,22,0.56))] p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex flex-wrap items-center gap-3">
                            <BadgeChip tone={card.accent}>{card.eyebrow}</BadgeChip>
                            {isSelected ? (
                              <BadgeChip tone="cyan">Current selection</BadgeChip>
                            ) : null}
                          </div>
                          <h3 className="mt-4 font-display text-[1.85rem] font-medium tracking-[-0.045em] text-app-text">
                            {card.title}
                          </h3>
                          <p className="mt-3 max-w-2xl text-sm leading-6 text-app-muted">
                            {card.description}
                          </p>
                        </div>

                        <div
                          className={cn(
                            "relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border",
                            isSelected
                              ? "border-app-cyan/35 bg-[rgba(15,216,255,0.12)] text-app-cyan"
                              : "border-white/10 bg-white/[0.03] text-app-muted"
                          )}
                        >
                          {card.value === "neo_smart" ? (
                            <SparkNodeIcon />
                          ) : (
                            <GridPulseIcon />
                          )}
                        </div>
                      </div>

                      <div className="mt-5 grid gap-2.5">
                        {card.bullets.map((bullet) => (
                          <div
                            key={bullet}
                            className="flex items-start gap-3 rounded-2xl border border-white/5 bg-white/[0.02] px-3.5 py-3"
                          >
                            <span
                              className={cn(
                                "mt-1 inline-flex h-2.5 w-2.5 shrink-0 rounded-full",
                                card.accent === "gold"
                                  ? "bg-app-gold shadow-[0_0_14px_rgba(216,186,103,0.55)]"
                                  : "bg-app-cyan shadow-[0_0_14px_rgba(15,216,255,0.55)]"
                              )}
                            />
                            <span className="text-sm leading-5 text-app-muted">
                              {bullet}
                            </span>
                          </div>
                        ))}
                      </div>

                      <div className="mt-auto flex items-center justify-between gap-4 pt-5">
                        <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                          {isBusy
                            ? "Saving selection..."
                            : isSelected
                              ? "Saved in backend"
                              : "Select mode"}
                        </div>
                        <div
                          className={cn(
                            "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs tracking-[0.18em]",
                            isSelected
                              ? "bg-[rgba(15,216,255,0.12)] text-app-cyan"
                              : "bg-white/[0.03] text-app-muted"
                          )}
                        >
                          <span
                            className={cn(
                              "inline-block h-2 w-2 rounded-full",
                              isSelected ? "bg-app-cyan" : "bg-white/20"
                            )}
                          />
                          {isSelected ? "Active" : "Available"}
                        </div>
                      </div>
                    </div>
                  </GlassPanel>
                </motion.button>
              </RevealOnScroll>
            );
          })}
        </div>
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

function SparkNodeIcon() {
  return (
    <svg
      className="h-6 w-6"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3v5" />
      <path d="m8.5 8.5 3.5 3.5" />
      <path d="M21 12h-5" />
      <path d="m15.5 15.5-3.5-3.5" />
      <path d="M12 21v-5" />
      <path d="m8.5 15.5 3.5-3.5" />
      <path d="M3 12h5" />
      <path d="m8.5 8.5 3.5 3.5" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

function GridPulseIcon() {
  return (
    <svg
      className="h-6 w-6"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="4" y="4" width="6" height="6" rx="1.2" />
      <rect x="14" y="4" width="6" height="6" rx="1.2" />
      <rect x="4" y="14" width="6" height="6" rx="1.2" />
      <rect x="14" y="14" width="6" height="6" rx="1.2" />
      <path d="M10 7h4" />
      <path d="M7 10v4" />
      <path d="M17 10v4" />
      <path d="M10 17h4" />
    </svg>
  );
}
