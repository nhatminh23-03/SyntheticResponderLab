"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { bootstrapNeoDemoStudy, saveStudyMode } from "@/lib/api";
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
        "Use a guided setup with Neo Smart defaults and prefilled context for a polished demo.",
      bullets: [
        "Best for a fast guided walkthrough",
        "Starts with Neo Smart context and survey defaults",
        "Great for demo-ready storytelling",
      ],
      accent: "gold",
    },
    {
      value: "general",
      eyebrow: "Custom Study",
      title: "General Custom Study",
      description:
        "Start from a blank setup so you can tailor each step to your own project.",
      bullets: [
        "Best for non-Neo use cases",
        "No prefilled demo assumptions",
        "Same simulation engine with full flexibility",
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
    setStudy,
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

      if (nextMode === "neo_smart") {
        const workspaceMessage = isSwitchingModes
          ? " Started a new study for this mode so you can continue with a clean setup."
          : "";
        const bootstrappedStudy = await bootstrapNeoDemoStudy(resolvedStudyId);
        setStudy(bootstrappedStudy);
        setSelectedMode("neo_smart");

        const previewWarnings =
          bootstrappedStudy.derived?.latest_persona_preview?.warning_messages ?? [];
        const previewMessage =
          previewWarnings.length > 0
            ? ` Persona preview completed with warnings: ${previewWarnings.join("; ")}`
            : " Audience, product, market, survey, experiment, and persona preview are ready for Interview Synthesis.";

        setStatusMessage(`Neo Smart Living Demo prepared.${workspaceMessage}${previewMessage}`);
        return;
      }

      const result = await saveStudyMode(resolvedStudyId, nextMode);
      setSelectedMode(result.value as StudyModeValue);

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
        ? " Started a new study for this mode so you can continue with a clean setup."
        : "";
      setStatusMessage(`${baseMessage}${workspaceMessage} Next steps are ready for your custom inputs.`);
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
      <div className="grid gap-8 lg:min-h-[calc(100svh-var(--nav-height)-1rem)] xl:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)] xl:items-center">
        <RevealOnScroll>
          <SectionHeader
            index={1}
            eyebrow="Study Setup"
            title="Choose how you want to start this study."
            description="Pick the path that fits your demo. Guided Demo loads Neo Smart defaults. Custom Study starts blank so you can build your own setup."
          />

          <div className="mt-6 space-y-4">
            <div className="flex flex-wrap gap-3">
              <BadgeChip tone="gold">Step 1 of 6</BadgeChip>
              <BadgeChip tone="cyan">Saves to study</BadgeChip>
            </div>



            <div className="min-h-10 text-sm">
              {errorMessage ? (
                <span className="text-app-gold">{errorMessage}</span>
              ) : statusMessage ? (
                <span className="text-app-cyan">{statusMessage}</span>
              ) : (
                <span className="text-app-muted">
                  Pick a mode to start with either a guided demo setup or a blank custom setup.
                </span>
              )}
            </div>

            <Button
              variant="secondary"
              onClick={() => scrollToSection("audience")}
              disabled={!selectedMode}
              className="w-full sm:w-auto"
            >
              Continue to Audience Setup
              <ArrowRightIcon />
            </Button>
          </div>
        </RevealOnScroll>

        <div className="grid gap-4 md:grid-cols-2">
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
                        ? "[border-color:var(--color-border-strong)] [background:var(--color-brand-primary-soft)] [box-shadow:var(--button-primary-shadow)]"
                        : "hover:[border-color:var(--color-border-strong)] hover:[background:var(--button-secondary-bg-hover)]"
                    )}
                  >
                    <div className="flex h-full flex-col rounded-[1.35rem] border border-app-border p-4 sm:rounded-[1.45rem] sm:p-5 [background:var(--theme-panel-gradient)]">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex flex-wrap items-center gap-3">
                            <BadgeChip tone={card.accent}>{card.eyebrow}</BadgeChip>
                            {isSelected ? (
                              <BadgeChip tone="cyan">Current selection</BadgeChip>
                            ) : null}
                          </div>
                          <h3 className="mt-4 font-display text-[1.55rem] font-medium tracking-[-0.045em] text-app-text sm:text-[1.7rem] lg:text-[1.85rem]">
                            {card.title}
                          </h3>
                          <p className="mt-3 max-w-2xl text-sm leading-6 text-app-muted">
                            {card.description}
                          </p>
                        </div>

                        <div
                          className={cn(
                            "relative flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border sm:h-12 sm:w-12",
                            isSelected
                              ? "text-app-cyan [border-color:var(--color-border-strong)] [background:var(--color-brand-primary-soft)]"
                              : "text-app-muted [border-color:var(--status-neutral-border)] [background:var(--status-neutral-bg)]"
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
                            className="flex items-start gap-3 rounded-2xl border border-app-border px-3 py-3 [background:var(--button-secondary-bg)] sm:px-3.5"
                          >
                            <span
                              className={cn(
                                "mt-1 inline-flex h-2.5 w-2.5 shrink-0 rounded-full",
                                card.accent === "gold"
                                  ? "bg-app-gold shadow-[var(--chip-gold-shadow)]"
                                  : "bg-app-cyan shadow-[var(--chip-cyan-shadow)]"
                              )}
                            />
                            <span className="text-sm leading-5 text-app-muted">
                              {bullet}
                            </span>
                          </div>
                        ))}
                      </div>

                      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-5">
                        <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                          {isBusy
                            ? "Saving mode..."
                            : isSelected
                              ? "Saved"
                              : "Choose mode"}
                        </div>
                        <div
                          className={cn(
                            "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs tracking-[0.18em]",
                            isSelected
                              ? "text-app-cyan [background:var(--color-brand-primary-soft)]"
                              : "text-app-muted [background:var(--status-neutral-bg)]"
                          )}
                        >
                          <span
                            className={cn(
                              "inline-block h-2 w-2 rounded-full",
                              isSelected ? "bg-app-cyan" : "[background:var(--status-neutral-border)]"
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
