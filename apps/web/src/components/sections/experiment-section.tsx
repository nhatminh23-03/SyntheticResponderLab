"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  ExperimentPayload,
  generatePersonaPreview,
  getModelCatalog,
  getPromptPreview,
  ModelCatalogEntry,
  PromptPreviewPayload,
  saveExperiment,
  WorkflowReadiness,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { Field, TextInput } from "@/components/ui/form-controls";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";

type ExperimentMode = "split" | "mirror" | "stability";

type ExperimentDraft = {
  sample_size: number;
  selected_models: string[];
  experiment_mode: ExperimentMode;
  reruns_per_persona: number;
};

type StatusTone = "neutral" | "success" | "warning" | "error";

type ExperimentStatusState = {
  tone: StatusTone;
  message: string;
};

const DEFAULT_MODEL_OPTIONS: ModelCatalogEntry[] = [
  { id: "openai/gpt-4o-mini", name: "openai/gpt-4o-mini" },
  { id: "anthropic/claude-sonnet-4.5", name: "anthropic/claude-sonnet-4.5" },
  { id: "google/gemini-2.5-flash", name: "google/gemini-2.5-flash" },
  { id: "anthropic/claude-haiku-4.5", name: "anthropic/claude-haiku-4.5" },
  { id: "google/gemini-2.5-pro", name: "google/gemini-2.5-pro" },
  { id: "openai/gpt-5", name: "openai/gpt-5" },
];

const DEFAULT_SELECTED_MODEL_IDS = [
  "openai/gpt-4o-mini",
  "anthropic/claude-sonnet-4.5",
];

const EXPERIMENT_MODE_OPTIONS: Array<{
  value: ExperimentMode;
  title: string;
  description: string;
}> = [
  {
    value: "split",
    title: "Split Sample",
    description:
      "Divide the sample across selected models to compare outputs efficiently.",
  },
  {
    value: "mirror",
    title: "Mirror Sample",
    description:
      "Have each selected model answer the same respondent set for direct comparison.",
  },
  {
    value: "stability",
    title: "Stability Sample",
    description:
      "Repeat runs to measure consistency and variability within the same model path.",
  },
];

const DEFAULT_DRAFT: ExperimentDraft = {
  sample_size: 100,
  selected_models: DEFAULT_SELECTED_MODEL_IDS,
  experiment_mode: "split",
  reruns_per_persona: 1,
};

const PERSONA_PREVIEW_SAMPLE_CAP = 12;
const SHOW_EXPERIMENT_SUMMARY_CARD = false;
const SHOW_LATEST_PERSONA_PREVIEW_CARD = false;

export function ExperimentSection() {
  const {
    studyId,
    study,
    createOrLoadStudy,
    isCreatingStudy,
    isHydratingStudy,
    refreshStudy,
  } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [workflow, setWorkflow] = useState<WorkflowReadiness | null>(null);
  const [draft, setDraft] = useState<ExperimentDraft>(DEFAULT_DRAFT);
  const [savedSnapshot, setSavedSnapshot] = useState("");
  const [hasSavedExperiment, setHasSavedExperiment] = useState(false);
  const [status, setStatus] = useState<ExperimentStatusState>({
    tone: "neutral",
    message: "Experiment settings are local until you save the execution plan.",
  });
  const [previewStatus, setPreviewStatus] = useState<ExperimentStatusState>({
    tone: "neutral",
    message:
      "Save the experiment plan first, then generate a persona preview as a realism check before Simulation UI exists.",
  });
  const [modelSearch, setModelSearch] = useState("");
  const [isAddModelControlsOpen, setIsAddModelControlsOpen] = useState(false);
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false);
  const [catalogModels, setCatalogModels] = useState<ModelCatalogEntry[]>(DEFAULT_MODEL_OPTIONS);
  const [catalogSource, setCatalogSource] = useState<"openrouter" | "fallback">("fallback");
  const [catalogWarning, setCatalogWarning] = useState<string | null>(null);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false);
  const [isRerunsInfoOpen, setIsRerunsInfoOpen] = useState(false);
  const [promptPreview, setPromptPreview] = useState<PromptPreviewPayload | null>(null);
  const [isLoadingPromptPreview, setIsLoadingPromptPreview] = useState(false);
  const [promptPreviewError, setPromptPreviewError] = useState<string | null>(null);
  const latestPreview = study?.derived?.latest_persona_preview ?? null;

  const loadModelCatalog = useCallback(async () => {
    setIsLoadingCatalog(true);
    try {
      const result = await getModelCatalog();
      setCatalogModels(resolveAllowedModelOptions(result.models));
      setCatalogSource(result.source);
      setCatalogWarning(result.warning);
    } catch (error) {
      setCatalogModels(DEFAULT_MODEL_OPTIONS);
      setCatalogSource("fallback");
      setCatalogWarning(
        error instanceof Error
          ? error.message
          : "Unable to load the model catalog right now."
      );
    } finally {
      setIsLoadingCatalog(false);
    }
  }, []);

  useEffect(() => {
    void loadModelCatalog();
  }, [loadModelCatalog]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateExperiment() {
      if (!studyId || !study) {
        if (!cancelled) {
          setWorkflow(null);
          setDraft(DEFAULT_DRAFT);
          setModelSearch("");
          setIsAddModelControlsOpen(false);
          setIsModelPickerOpen(false);
          setIsRerunsInfoOpen(false);
          setPromptPreview(null);
          setPromptPreviewError(null);
          setSavedSnapshot("");
          setHasSavedExperiment(false);
          setStatus({
            tone: "neutral",
            message: "Experiment settings are local until you save the execution plan.",
          });
          setPreviewStatus({
            tone: "neutral",
            message:
              "Save the experiment plan first, then generate a persona preview as a realism check before Simulation UI exists.",
          });
        }
        return;
      }

      const hasSaved = study.experiment?.status === "saved" && !!study.experiment?.value;
      const nextDraft = hasSaved
        ? experimentPayloadToDraft(study.experiment?.value)
        : DEFAULT_DRAFT;
      const latestPreview = study.derived?.latest_persona_preview ?? null;

      if (!cancelled) {
        setWorkflow(study.derived?.workflow ?? null);
        setDraft(nextDraft);
        setModelSearch("");
        setIsAddModelControlsOpen(false);
        setIsModelPickerOpen(false);
        setIsRerunsInfoOpen(false);
        setSavedSnapshot(
          hasSaved ? JSON.stringify(experimentDraftToPayload(nextDraft)) : ""
        );
        setHasSavedExperiment(hasSaved);
        setPromptPreview(null);
        setPromptPreviewError(null);
        setStatus({
          tone: hasSaved ? "success" : "neutral",
          message: hasSaved
            ? "Saved experiment plan loaded from the current study."
            : "Experiment settings are local until you save the execution plan.",
        });
        setPreviewStatus(buildPreviewStatus(latestPreview, hasSaved));
      }
    }

    void hydrateExperiment();

    return () => {
      cancelled = true;
    };
  }, [
    studyId,
    study?.experiment?.updated_at,
    study?.experiment?.status,
    study?.derived?.latest_persona_preview?.completed_at,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function hydratePromptPreview() {
      if (!studyId || !latestPreview?.personas?.length) {
        if (!cancelled) {
          setPromptPreview(null);
          setPromptPreviewError(null);
        }
        return;
      }

      setIsLoadingPromptPreview(true);
      try {
        const result = await getPromptPreview(studyId, 0);
        if (!cancelled) {
          setPromptPreview(result);
          setPromptPreviewError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setPromptPreview(null);
          setPromptPreviewError(
            error instanceof Error
              ? error.message
              : "Unable to load prompt preview right now."
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoadingPromptPreview(false);
        }
      }
    }

    void hydratePromptPreview();

    return () => {
      cancelled = true;
    };
  }, [studyId, latestPreview?.completed_at, latestPreview?.personas?.length]);

  const draftPayload = useMemo(() => experimentDraftToPayload(draft), [draft]);
  const isDirty = JSON.stringify(draftPayload) !== savedSnapshot;
  const validationMessage = validateExperimentDraft(draft);
  const currentMode = EXPERIMENT_MODE_OPTIONS.find(
    (option) => option.value === draft.experiment_mode
  );
  const previewWarnings = latestPreview?.warning_messages ?? [];
  const previewPersonas = latestPreview?.personas?.slice(0, 4) ?? [];
  const previewSampleSize = Math.min(
    Math.max(draft.sample_size, 1),
    PERSONA_PREVIEW_SAMPLE_CAP
  );
  const availableModels = catalogModels.length > 0 ? catalogModels : DEFAULT_MODEL_OPTIONS;
  const showExperimentSidebar =
    SHOW_EXPERIMENT_SUMMARY_CARD || SHOW_LATEST_PERSONA_PREVIEW_CARD;
  const rerunsCap = useMemo(
    () => getRerunCap(draft.sample_size, draft.selected_models.length),
    [draft.sample_size, draft.selected_models.length]
  );
  const rerunsMax = useMemo(
    () =>
      getEffectiveRerunMax(
        draft.experiment_mode,
        draft.sample_size,
        draft.selected_models.length
      ),
    [draft.experiment_mode, draft.sample_size, draft.selected_models.length]
  );
  const filteredModelOptions = useMemo(() => {
    const query = modelSearch.trim().toLowerCase();
    return availableModels.filter((model) => {
      const modelId = model.id.toLowerCase();
      const modelName = (model.name ?? model.id).toLowerCase();
      return (
        !draft.selected_models.includes(model.id) &&
        (query.length === 0 || modelId.includes(query) || modelName.includes(query))
      );
    });
  }, [availableModels, draft.selected_models, modelSearch]);

  useEffect(() => {
    setDraft((current) => {
      const nextReruns = normalizeReruns(
        current.experiment_mode,
        current.sample_size,
        current.selected_models.length,
        current.reruns_per_persona
      );

      if (nextReruns === current.reruns_per_persona) {
        return current;
      }

      return {
        ...current,
        reruns_per_persona: nextReruns,
      };
    });
  }, [draft.experiment_mode, draft.sample_size, draft.selected_models.length]);

  function updateDraft<K extends keyof ExperimentDraft>(
    key: K,
    value: ExperimentDraft[K]
  ) {
    setDraft((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function handleClearPlan() {
    setDraft(DEFAULT_DRAFT);
    setModelSearch("");
    setIsAddModelControlsOpen(false);
    setIsModelPickerOpen(false);
    setIsRerunsInfoOpen(false);
    setStatus({
      tone: "warning",
      message:
        "The backend does not expose a clear experiment-plan endpoint yet. The form was reset locally; save again if you want to overwrite the persisted plan.",
    });
  }

  function closeModelControls() {
    setIsAddModelControlsOpen(false);
    setModelSearch("");
    setIsModelPickerOpen(false);
  }

  function openModelControls() {
    setIsAddModelControlsOpen(true);
  }

  function handleAddModel(model: string) {
    const nextModel = model.trim();
    if (
      !nextModel ||
      draft.selected_models.includes(nextModel) ||
      !DEFAULT_MODEL_OPTIONS.some((entry) => entry.id === nextModel)
    ) {
      return;
    }

    updateDraft("selected_models", [...draft.selected_models, nextModel]);
    setModelSearch("");
    setIsModelPickerOpen(false);
  }

  function handleRemoveModel(model: string) {
    updateDraft(
      "selected_models",
      draft.selected_models.filter((entry) => entry !== model)
    );
  }

  function handleSampleSizeStep(delta: number) {
    updateDraft("sample_size", Math.max(1, draft.sample_size + delta));
  }

  function handleRerunsStep(delta: number) {
    updateDraft(
      "reruns_per_persona",
      normalizeReruns(
        draft.experiment_mode,
        draft.sample_size,
        draft.selected_models.length,
        draft.reruns_per_persona + delta
      )
    );
  }

  function handleExperimentModeChange(nextMode: ExperimentMode) {
    setDraft((current) => ({
      ...current,
      experiment_mode: nextMode,
      reruns_per_persona: normalizeReruns(
        nextMode,
        current.sample_size,
        current.selected_models.length,
        current.reruns_per_persona
      ),
    }));
  }

  async function handleSavePlan() {
    const nextValidationMessage = validateExperimentDraft(draft);
    if (nextValidationMessage) {
      setStatus({
        tone: "error",
        message: nextValidationMessage,
      });
      return;
    }

    setIsSaving(true);
    setStatus({
      tone: "neutral",
      message: "Saving experiment plan...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await saveExperiment(resolvedStudyId, draftPayload);
      await refreshStudy(resolvedStudyId);
      setSavedSnapshot(JSON.stringify(draftPayload));
      setHasSavedExperiment(true);
      setWorkflow(result.workflow ?? null);
      setStatus({
        tone: "success",
        message: "Experiment plan saved successfully.",
      });
      if (!latestPreview) {
        setPreviewStatus({
          tone: "neutral",
          message:
            "Experiment plan saved. Generate a persona preview to verify grounding quality before the later run flow.",
        });
      }
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to save the experiment plan right now.",
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleGeneratePreview() {
    setIsGeneratingPreview(true);
    setPreviewStatus({
      tone: "neutral",
      message: "Generating persona preview...",
    });

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;

      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await generatePersonaPreview(resolvedStudyId, {
        sample_size: previewSampleSize,
        use_grounded_priors: true,
        use_geography_filtered_priors: true,
        use_cex_affordability_priors: true,
      });
      await refreshStudy(resolvedStudyId);
      setWorkflow(result.workflow ?? null);
      setPreviewStatus(
        result.personaPreview?.warning_messages?.length
          ? {
              tone: "warning",
              message:
                "Persona preview completed with warnings. Review degraded grounding and missing-context notes before moving on.",
            }
          : {
              tone: "success",
              message: "Persona preview completed successfully.",
            }
      );
      scrollToSection("run-simulation");
    } catch (error) {
      setPreviewStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to generate persona preview right now.",
      });
    } finally {
      setIsGeneratingPreview(false);
    }
  }

  const isBusy = isCreatingStudy || isHydratingStudy || isSaving;
  const inlineStatusMessage =
    validationMessage ??
    (status.tone === "success" || status.tone === "warning" || status.tone === "error"
      ? status.message
      : null);
  const inlineStatusTone: StatusTone = validationMessage ? "error" : status.tone;
  const rerunsInfoMessage =
    draft.experiment_mode === "stability"
      ? `Stability Sample defaults to 2 reruns per persona. Current max is ${rerunsCap} based on sample size ${draft.sample_size} and ${draft.selected_models.length} selected model${draft.selected_models.length === 1 ? "" : "s"}.`
      : `Default reruns is 1 per persona. Current max is ${rerunsCap} based on sample size ${draft.sample_size} and ${draft.selected_models.length} selected model${draft.selected_models.length === 1 ? "" : "s"}.`;

  return (
    <SectionWrapper
      id="experiment"
      scrollable
      contentClassName="relative scrollbar-hidden"
    >
      <div
        className={cn(
          "grid items-start gap-6",
          showExperimentSidebar &&
            "lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1.02fr)_22rem] 2xl:grid-cols-[minmax(0,1.03fr)_28rem]"
        )}
      >
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={6}
              eyebrow="Experiment Design"
              title="Define how this study should execute."
              description="Choose the scale, model set, and comparison strategy that will govern the later simulation. This chapter now saves into canonical backend study state and also houses persona preview as a pre-run grounding check."
            />

            <div className="mt-5 flex flex-wrap gap-3">
              <Button variant="secondary" onClick={handleClearPlan}>
                Clear Saved Experiment Plan
              </Button>
              <Button
                variant="secondary"
                onClick={() => void loadModelCatalog()}
                disabled={isLoadingCatalog}
              >
                {isLoadingCatalog ? "Refreshing Model Catalog..." : "Refresh Model Catalog"}
              </Button>
              <BadgeChip tone={hasSavedExperiment ? "cyan" : "gold"}>
                {hasSavedExperiment ? "Saved in backend" : "Unsaved experiment"}
              </BadgeChip>
            </div>
          </RevealOnScroll>

          <div>
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                  Execution Inputs
                </div>

                <div className="mt-5 space-y-6">
                  <div className="grid items-start gap-5 lg:grid-cols-4">
                    <Field
                      label="Sample Size"
                      className="lg:col-span-1"
                    >
                      <NumericControl
                        value={draft.sample_size}
                        onChange={(value) =>
                          updateDraft("sample_size", Math.max(1, value))
                        }
                        onStep={handleSampleSizeStep}
                        min={1}
                      />
                    </Field>

                    <Field
                      label="Select Model(s)"
                      className="lg:col-span-2"
                    >
                      <div className="relative">
                        <div className="grid gap-3 lg:grid-cols-3">
                          {draft.selected_models.length > 0 ? (
                            draft.selected_models.map((model) => (
                              <button
                                key={model}
                                type="button"
                                onClick={() => handleRemoveModel(model)}
                                className="inline-flex w-full items-center justify-between gap-2 rounded-full border border-app-cyan/20 bg-[rgba(15,216,255,0.08)] px-4 py-3 text-sm text-app-cyan transition hover:border-app-cyan/35"
                              >
                                <span>{model}</span>
                                <span className="text-app-text/70">×</span>
                              </button>
                            ))
                          ) : (
                            <span className="text-sm text-app-muted">
                              No models selected yet.
                            </span>
                          )}

                          <Button
                            variant="secondary"
                            onClick={
                              isAddModelControlsOpen ? closeModelControls : openModelControls
                            }
                            aria-expanded={isAddModelControlsOpen}
                            aria-controls="experiment-model-controls"
                            className="w-full min-w-0"
                          >
                            Add Model
                          </Button>
                        </div>

                        {isAddModelControlsOpen ? (
                          <div
                            id="experiment-model-controls"
                            className="absolute left-0 right-0 top-[calc(100%+0.75rem)] z-30 rounded-[1.45rem] border border-white/8 bg-[rgba(12,18,22,0.96)] p-4 shadow-[0_22px_60px_rgba(0,0,0,0.45)] backdrop-blur-xl lg:left-auto lg:w-full"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <BadgeChip tone="cyan">Available model options</BadgeChip>
                                {catalogWarning ? (
                                  <BadgeChip tone="gold">Catalog warning</BadgeChip>
                                ) : null}
                              </div>

                              <Button
                                variant="secondary"
                                onClick={closeModelControls}
                                className="min-w-[6.5rem]"
                              >
                                Done
                              </Button>
                            </div>

                            {catalogWarning ? (
                              <p className="mt-3 text-sm leading-6 text-app-muted">
                                {catalogWarning}
                              </p>
                            ) : null}

                            <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                              <TextInput
                                value={modelSearch}
                                onChange={(value) => {
                                  setModelSearch(value);
                                  if (value.trim()) {
                                    setIsModelPickerOpen(true);
                                  }
                                }}
                                placeholder="Search or paste a model ID"
                              />
                              <Button
                                variant="secondary"
                                onClick={() => handleAddModel(modelSearch)}
                                disabled={!modelSearch.trim()}
                              >
                                Add Model
                              </Button>
                            </div>

                            <div className="mt-3">
                              <button
                                type="button"
                                onClick={() => setIsModelPickerOpen((current) => !current)}
                                className="flex w-full items-center justify-between rounded-[1.2rem] border border-white/8 bg-white/[0.03] px-4 py-3 text-left text-sm text-app-text transition hover:border-app-cyan/25"
                              >
                                <span>
                                  {isModelPickerOpen
                                    ? "Hide model catalog options"
                                    : "Choose from available model catalog"}
                                </span>
                                <span className="text-app-muted">
                                  {isModelPickerOpen ? "−" : "+"}
                                </span>
                              </button>

                              {isModelPickerOpen ? (
                                <div className="fine-scrollbar mt-3 max-h-48 overflow-y-auto rounded-[1.2rem] border border-white/8 bg-black/15 p-3">
                                  <div className="flex flex-wrap gap-2">
                                    {filteredModelOptions.length > 0 ? (
                                      filteredModelOptions.map((model) => (
                                        <button
                                          key={model.id}
                                          type="button"
                                          onClick={() => handleAddModel(model.id)}
                                          className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-app-muted transition hover:border-app-cyan/25 hover:text-app-text"
                                        >
                                          {model.id}
                                        </button>
                                      ))
                                    ) : (
                                      <span className="px-1 text-sm text-app-muted">
                                        No additional models match the current search.
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </Field>

                    <div className="relative lg:col-span-1">
                      <div className="mb-2 flex items-center gap-2">
                        <span className="text-sm font-medium text-app-text">
                          Reruns Per Persona
                        </span>
                        <button
                          type="button"
                          onClick={() => setIsRerunsInfoOpen((current) => !current)}
                          aria-expanded={isRerunsInfoOpen}
                          aria-label="Show reruns help"
                          className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-[0.72rem] font-medium text-app-muted transition hover:border-app-cyan/25 hover:text-app-cyan"
                        >
                          i
                        </button>
                      </div>

                      {isRerunsInfoOpen ? (
                        <div className="absolute right-0 top-full z-20 mt-2 w-[19rem] rounded-[1.15rem] border border-white/8 bg-[rgba(12,18,22,0.96)] p-4 text-sm leading-6 text-app-muted shadow-[0_18px_44px_rgba(0,0,0,0.38)] backdrop-blur-xl">
                          {rerunsInfoMessage}
                        </div>
                      ) : null}

                      <NumericControl
                        value={draft.reruns_per_persona}
                        onChange={(value) =>
                          updateDraft(
                            "reruns_per_persona",
                            normalizeReruns(
                              draft.experiment_mode,
                              draft.sample_size,
                              draft.selected_models.length,
                              value
                            )
                          )
                        }
                        onStep={handleRerunsStep}
                        min={getMinimumReruns(draft.experiment_mode)}
                        max={rerunsMax}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="mb-3 text-sm font-medium text-app-text">
                      Experiment Mode
                    </div>
                    <div className="grid gap-3 lg:grid-cols-3">
                      {EXPERIMENT_MODE_OPTIONS.map((option) => {
                        const selected = draft.experiment_mode === option.value;
                        return (
                          <button
                            key={option.value}
                            type="button"
                            onClick={() => handleExperimentModeChange(option.value)}
                            className={cn(
                              "rounded-[1.45rem] border p-5 text-left transition",
                              selected
                                ? "border-app-cyan/30 bg-[rgba(15,216,255,0.08)] shadow-[0_0_0_4px_rgba(15,216,255,0.06)]"
                                : "border-white/8 bg-white/[0.03] hover:border-white/14"
                            )}
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <BadgeChip tone={selected ? "cyan" : "neutral"}>
                                {option.title}
                              </BadgeChip>
                              {selected ? <BadgeChip tone="gold">Selected</BadgeChip> : null}
                            </div>
                            <p className="mt-4 text-sm leading-6 text-app-muted">
                              {option.description}
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                    <Button
                      onClick={handleSavePlan}
                      disabled={isBusy}
                    >
                      {isSaving ? "Saving Experiment..." : "Save Experiment Plan"}
                    </Button>
                    <BadgeChip tone={hasSavedExperiment ? "cyan" : "gold"}>
                      {hasSavedExperiment ? "Saved state" : "Unsaved experiment"}
                    </BadgeChip>
                    <BadgeChip tone={isDirty ? "gold" : "neutral"}>
                      {isDirty ? "Unsaved edits" : "No new local edits"}
                    </BadgeChip>
                  </div>

                  {inlineStatusMessage ? (
                    <p
                      className={cn(
                        "text-sm leading-6",
                        inlineStatusTone === "success" && "text-app-cyan",
                        (inlineStatusTone === "warning" || inlineStatusTone === "error") &&
                          "text-app-gold",
                        inlineStatusTone === "neutral" && "text-app-muted"
                      )}
                    >
                      {inlineStatusMessage}
                    </p>
                  ) : null}
                </div>
              </div>
            </GlassPanel>
          </div>

          <div>
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <BadgeChip tone="gold">Persona Preview</BadgeChip>
                  <BadgeChip>{`Uses ${previewSampleSize} persona${previewSampleSize === 1 ? "" : "s"} max`}</BadgeChip>
                  {latestPreview ? <BadgeChip tone="cyan">Latest preview loaded</BadgeChip> : null}
                </div>

                <p className="mt-4 max-w-2xl text-sm leading-6 text-app-muted">
                  Persona preview is the final setup check before Simulation UI. It uses the saved audience plus grounded priors, geography, and affordability context where available, then stores the latest preview back into canonical study state.
                </p>

                <div
                  className={cn(
                    "mt-5 rounded-2xl border px-4 py-3 text-sm leading-6",
                    previewStatus.tone === "success" &&
                      "border-app-cyan/20 bg-[rgba(15,216,255,0.08)] text-app-cyan",
                    previewStatus.tone === "warning" &&
                      "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                    previewStatus.tone === "error" &&
                      "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                    previewStatus.tone === "neutral" &&
                      "border-white/8 bg-white/[0.03] text-app-muted"
                  )}
                >
                  {previewStatus.message}
                </div>

                <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                  <Button
                    onClick={handleGeneratePreview}
                    disabled={
                      isGeneratingPreview ||
                      isSaving ||
                      isCreatingStudy ||
                      isHydratingStudy ||
                      !workflow?.ready_for_persona_preview
                    }
                  >
                    {isGeneratingPreview
                      ? "Generating Preview..."
                      : "Generate Persona Preview"}
                  </Button>
                  <BadgeChip tone={workflow?.ready_for_persona_preview ? "cyan" : "gold"}>
                    {workflow?.ready_for_persona_preview
                      ? "Setup ready for preview"
                      : "Save the full setup stack first"}
                  </BadgeChip>
                </div>

                <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <BadgeChip tone="cyan">Prompt Preview</BadgeChip>
                    {promptPreview ? (
                      <BadgeChip>{promptPreview.persona_label ?? `Persona ${promptPreview.persona_index + 1}`}</BadgeChip>
                    ) : null}
                    {isLoadingPromptPreview ? <BadgeChip>Loading</BadgeChip> : null}
                  </div>

                  <p className="mt-3 text-sm leading-6 text-app-muted">
                    This shows the actual prompt scaffold for the first preview persona. If you run 100 samples, each persona uses this same structure and only the persona section changes.
                  </p>

                  {promptPreview ? (
                    <details className="mt-4 rounded-[1.2rem] border border-white/8 bg-[rgba(8,12,16,0.6)] p-4">
                      <summary className="cursor-pointer list-none text-sm font-medium text-app-text">
                        Show first-persona prompt preview
                      </summary>
                      <div className="mt-4 grid gap-4 xl:grid-cols-2">
                        <div className="rounded-[1rem] border border-white/6 bg-black/20 p-4">
                          <div className="text-[0.72rem] uppercase tracking-[0.22em] text-app-muted">
                            System
                          </div>
                          <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-xs leading-6 text-app-text">
                            {promptPreview.system_instruction}
                          </pre>
                        </div>
                        <div className="rounded-[1rem] border border-white/6 bg-black/20 p-4">
                          <div className="text-[0.72rem] uppercase tracking-[0.22em] text-app-muted">
                            User
                          </div>
                          <pre className="mt-3 max-h-[28rem] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-app-text">
                            {promptPreview.user_instruction}
                          </pre>
                        </div>
                      </div>
                    </details>
                  ) : (
                    <div className="mt-4 rounded-[1.2rem] border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm leading-6 text-app-muted">
                      {promptPreviewError
                        ? promptPreviewError
                        : latestPreview
                          ? "Prompt preview will load from the latest persona preview."
                          : "Generate a persona preview first to inspect the prompt."}
                    </div>
                  )}
                </div>
              </div>
            </GlassPanel>
          </div>
        </div>

        {showExperimentSidebar ? (
          <div className="min-w-0 lg:sticky lg:top-6 lg:w-full lg:max-w-[20rem] lg:justify-self-end xl:max-w-[22rem] 2xl:max-w-[28rem]">
            <div className="space-y-5">
              {SHOW_EXPERIMENT_SUMMARY_CARD ? (
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                    <div className="flex flex-wrap gap-2">
                      <BadgeChip tone="cyan">Execution Summary</BadgeChip>
                      <BadgeChip tone={hasSavedExperiment ? "cyan" : "gold"}>
                        {hasSavedExperiment ? "Saved to backend" : "Unsaved experiment"}
                      </BadgeChip>
                    </div>

                    <div className="mt-5 grid gap-3 sm:grid-cols-2">
                      <MetaCard label="Sample Size" value={String(draft.sample_size)} />
                      <MetaCard
                        label="Model Count"
                        value={String(draft.selected_models.length)}
                      />
                      <MetaCard
                        label="Experiment Mode"
                        value={currentMode?.title ?? "Not set"}
                      />
                      <MetaCard
                        label="Reruns"
                        value={`${draft.reruns_per_persona} per persona`}
                      />
                    </div>

                    <div className="mt-5">
                      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                        Selected Models
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {draft.selected_models.length > 0 ? (
                          draft.selected_models.map((model) => (
                            <BadgeChip key={model}>{model}</BadgeChip>
                          ))
                        ) : (
                          <span className="text-sm text-app-muted">
                            Add at least one model to define the execution plan.
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4">
                      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                        What this plan means
                      </div>
                      <p className="mt-3 text-sm leading-7 text-app-text">
                        {buildExperimentNarrative(draft)}
                      </p>
                    </div>
                  </div>
                </GlassPanel>
              ) : null}

              {SHOW_LATEST_PERSONA_PREVIEW_CARD ? (
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                    <div className="flex flex-wrap gap-2">
                      <BadgeChip tone="gold">Latest Persona Preview</BadgeChip>
                      {latestPreview ? (
                        <BadgeChip tone={previewWarnings.length > 0 ? "gold" : "cyan"}>
                          {previewWarnings.length > 0 ? "Warnings present" : "Healthy preview"}
                        </BadgeChip>
                      ) : (
                        <BadgeChip>No preview yet</BadgeChip>
                      )}
                    </div>

                    {latestPreview ? (
                      <>
                        <div className="mt-5 grid gap-3 sm:grid-cols-2">
                          <MetaCard
                            label="Preview Size"
                            value={String(latestPreview.personas?.length ?? 0)}
                          />
                          <MetaCard
                            label="Generation Mode"
                            value={latestPreview.generation_mode ?? "Unknown"}
                          />
                        </div>

                        {previewWarnings.length > 0 ? (
                          <div className="mt-5 rounded-[1.35rem] border border-app-gold/20 bg-[rgba(216,186,103,0.08)] p-4">
                            <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-gold">
                              Preview warnings
                            </div>
                            <ul className="mt-3 space-y-2 text-sm leading-6 text-app-muted">
                              {previewWarnings.map((warning) => (
                                <li key={warning} className="flex gap-2">
                                  <span className="mt-2 inline-flex h-2 w-2 rounded-full bg-app-gold" />
                                  <span>{warning}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}

                        <div className="mt-5 space-y-3">
                          {previewPersonas.length > 0 ? (
                            previewPersonas.map((persona, index) => (
                              <div
                                key={String(persona.persona_id ?? index)}
                                className="rounded-[1.35rem] border border-white/6 bg-white/[0.03] p-4"
                              >
                                <div className="flex flex-wrap items-center justify-between gap-3">
                                  <div>
                                    <div className="text-sm font-medium text-app-text">
                                      {toOptionalString(persona.segment_label) ||
                                        toOptionalString(persona.persona_id) ||
                                        `Persona ${index + 1}`}
                                    </div>
                                    <div className="mt-1 text-sm text-app-muted">
                                      {[
                                        toOptionalString(persona.fit_tier),
                                        toOptionalString(persona.generation_mode),
                                      ]
                                        .filter(Boolean)
                                        .join(" • ") || "Grounded preview persona"}
                                    </div>
                                  </div>
                                  <BadgeChip>{`P${index + 1}`}</BadgeChip>
                                </div>

                                <p className="mt-3 text-sm leading-6 text-app-muted">
                                  {buildPersonaSnippet(persona)}
                                </p>
                              </div>
                            ))
                          ) : (
                            <div className="rounded-[1.35rem] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8 text-sm leading-6 text-app-muted">
                              Preview metadata is saved, but no persona rows were returned.
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="mt-5 rounded-[1.35rem] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8 text-sm leading-6 text-app-muted">
                        Save the experiment plan, then generate a persona preview to inspect grounding quality before building Simulation UI.
                      </div>
                    )}
                  </div>
                </GlassPanel>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </SectionWrapper>
  );
}

function dedupeModels(models: ModelCatalogEntry[]) {
  const seen = new Set<string>();
  return models.filter((model) => {
    if (!model.id || seen.has(model.id)) {
      return false;
    }
    seen.add(model.id);
    return true;
  });
}

function resolveAllowedModelOptions(models: ModelCatalogEntry[]) {
  const dedupedModels = dedupeModels(models);

  return DEFAULT_MODEL_OPTIONS.map((fallbackModel) => {
    const matchedModel = dedupedModels.find((model) => model.id === fallbackModel.id);
    return matchedModel ?? fallbackModel;
  });
}

function experimentPayloadToDraft(
  value?: ExperimentPayload | null
): ExperimentDraft {
  const allowedModelIds = new Set(DEFAULT_MODEL_OPTIONS.map((model) => model.id));
  const selectedModels = Array.isArray(value?.selected_models)
    ? value?.selected_models.filter(
        (model): model is string =>
          typeof model === "string" &&
          model.trim().length > 0 &&
          allowedModelIds.has(model)
      )
    : [];
  const experimentMode =
    value?.experiment_mode === "split" ||
    value?.experiment_mode === "mirror" ||
    value?.experiment_mode === "stability"
      ? value.experiment_mode
      : DEFAULT_DRAFT.experiment_mode;
  const normalizedSelectedModels =
    selectedModels.length >= 2 ? selectedModels : DEFAULT_SELECTED_MODEL_IDS;

  return {
    sample_size:
      typeof value?.sample_size === "number" && value.sample_size > 0
        ? value.sample_size
        : DEFAULT_DRAFT.sample_size,
    selected_models: normalizedSelectedModels,
    experiment_mode: experimentMode,
    reruns_per_persona:
      normalizeReruns(
        experimentMode,
        typeof value?.sample_size === "number" && value.sample_size > 0
          ? value.sample_size
          : DEFAULT_DRAFT.sample_size,
        normalizedSelectedModels.length,
        typeof value?.reruns_per_persona === "number" && value.reruns_per_persona > 0
          ? value.reruns_per_persona
          : DEFAULT_DRAFT.reruns_per_persona
      ),
  };
}

function experimentDraftToPayload(draft: ExperimentDraft): ExperimentPayload {
  return {
    sample_size: draft.sample_size,
    selected_models: draft.selected_models,
    experiment_mode: draft.experiment_mode,
    reruns_per_persona: draft.reruns_per_persona,
    mirror_personas_across_models: draft.experiment_mode === "mirror",
    split_across_models: draft.experiment_mode === "split",
    notes: null,
  };
}

function buildPreviewStatus(
  preview:
    | {
        warning_messages?: string[];
      }
    | null,
  hasSavedExperiment: boolean
): ExperimentStatusState {
  if (preview?.warning_messages?.length) {
    return {
      tone: "warning",
      message:
        "Latest persona preview is loaded with warnings. Review degraded grounding and missing-context notes before moving on.",
    };
  }

  if (preview) {
    return {
      tone: "success",
      message: "Latest persona preview is loaded from backend study state.",
    };
  }

  if (hasSavedExperiment) {
    return {
      tone: "neutral",
      message:
        "Experiment plan is saved. Generate a persona preview to verify grounding quality before the later run flow.",
    };
  }

  return {
    tone: "neutral",
    message:
      "Save the experiment plan first, then generate a persona preview as a realism check before Simulation UI exists.",
  };
}

function validateExperimentDraft(draft: ExperimentDraft) {
  if (draft.sample_size < 1) {
    return "Sample size must be at least 1.";
  }

  if (draft.selected_models.length < 2) {
    return "Select at least 2 models.";
  }

  const minimumSampleSize = getMinimumSampleSizeForDraft(
    draft.experiment_mode,
    draft.selected_models.length
  );

  if (draft.sample_size < minimumSampleSize) {
    return draft.experiment_mode === "stability"
      ? `Sample size must be at least ${minimumSampleSize} to support Stability Sample with ${draft.selected_models.length} selected models.`
      : `Sample size must be at least ${minimumSampleSize} for ${draft.selected_models.length} selected models.`;
  }

  if (draft.experiment_mode === "stability" && draft.reruns_per_persona < 2) {
    return "Stability Sample requires reruns per persona to be at least 2.";
  }

  const rerunCap = getRerunCap(draft.sample_size, draft.selected_models.length);
  if (draft.reruns_per_persona > rerunCap) {
    return `Reruns per persona cannot exceed ${rerunCap} for the current sample size and selected model count.`;
  }

  return null;
}

function buildExperimentNarrative(draft: ExperimentDraft) {
  const modelLead =
    draft.selected_models.length > 0
      ? summarizeList(draft.selected_models, 2)
      : "no selected models yet";

  if (draft.experiment_mode === "split") {
    return `Split Sample will divide ${draft.sample_size} planned respondents across ${modelLead}, giving you an efficient side-by-side comparison without every model answering every persona.`;
  }

  if (draft.experiment_mode === "mirror") {
    return `Mirror Sample will have ${modelLead} answer the same respondent set, making direct model-to-model comparison clearer at the cost of more total executions.`;
  }

  return `Stability Sample will repeat each persona ${draft.reruns_per_persona} time${draft.reruns_per_persona === 1 ? "" : "s"} using ${modelLead}, helping you inspect consistency and variability across repeated runs.`;
}

function getMinimumReruns(experimentMode: ExperimentMode) {
  return experimentMode === "stability" ? 2 : 1;
}

function getMinimumSampleSizeForDraft(
  experimentMode: ExperimentMode,
  selectedModelCount: number
) {
  return Math.max(1, selectedModelCount) * getMinimumReruns(experimentMode);
}

function getRerunCap(sampleSize: number, selectedModelCount: number) {
  if (selectedModelCount <= 0) {
    return Math.max(1, sampleSize);
  }

  return Math.max(1, Math.floor(sampleSize / selectedModelCount));
}

function getEffectiveRerunMax(
  experimentMode: ExperimentMode,
  sampleSize: number,
  selectedModelCount: number
) {
  return Math.max(
    getMinimumReruns(experimentMode),
    getRerunCap(sampleSize, selectedModelCount)
  );
}

function normalizeReruns(
  experimentMode: ExperimentMode,
  sampleSize: number,
  selectedModelCount: number,
  rerunsPerPersona: number
) {
  const nextValue = Number.isFinite(rerunsPerPersona) ? rerunsPerPersona : 0;
  const minimum = getMinimumReruns(experimentMode);
  const maximum = getEffectiveRerunMax(
    experimentMode,
    sampleSize,
    selectedModelCount
  );

  return Math.min(maximum, Math.max(minimum, nextValue));
}

function summarizeList(values: string[], maxVisible: number) {
  const visible = values.slice(0, maxVisible);
  if (values.length <= maxVisible) {
    return visible.join(" and ");
  }
  return `${visible.join(", ")}, and more`;
}

function buildPersonaSnippet(persona: Record<string, unknown>) {
  const parts = [
    toOptionalString(persona.age_bucket) || toOptionalString(persona.age_band),
    toOptionalString(persona.income_bucket) || toOptionalString(persona.income_band),
    toOptionalString(persona.home_type),
    toOptionalString(persona.work_mode),
  ].filter(Boolean);

  if (parts.length > 0) {
    return parts.join(" • ");
  }

  return "Preview persona details loaded from the backend preview payload.";
}

function toOptionalString(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function NumericControl({
  value,
  onChange,
  onStep,
  min,
  max,
}: {
  value: number;
  onChange: (value: number) => void;
  onStep: (delta: number) => void;
  min: number;
  max?: number;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => onStep(-1)}
        disabled={value <= min}
        className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan disabled:cursor-not-allowed disabled:opacity-45"
      >
        −
      </button>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => {
          const parsedValue = Number(event.target.value || min);
          const nextValue = Number.isFinite(parsedValue) ? parsedValue : min;
          const clampedValue =
            max == null
              ? Math.max(min, nextValue)
              : Math.min(max, Math.max(min, nextValue));

          onChange(clampedValue);
        }}
        className="w-full rounded-2xl border border-white/8 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm text-app-text outline-none transition focus:border-app-cyan/35 focus:bg-[rgba(255,255,255,0.05)] focus:shadow-[0_0_0_4px_rgba(15,216,255,0.08)]"
      />
      <button
        type="button"
        onClick={() => onStep(1)}
        disabled={max != null && value >= max}
        className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan disabled:cursor-not-allowed disabled:opacity-45"
      >
        +
      </button>
    </div>
  );
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.15rem] border border-white/6 bg-white/[0.03] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
      <div className="mt-2 text-sm leading-6 text-app-text">{value}</div>
    </div>
  );
}
