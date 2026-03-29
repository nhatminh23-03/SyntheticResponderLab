"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  ExperimentPayload,
  generatePersonaPreview,
  getModelCatalog,
  ModelCatalogEntry,
  saveExperiment,
  WorkflowReadiness,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { Field, TextAreaInput, TextInput } from "@/components/ui/form-controls";
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
  notes: string;
};

type StatusTone = "neutral" | "success" | "warning" | "error";

type ExperimentStatusState = {
  tone: StatusTone;
  message: string;
};

const DEFAULT_MODEL_OPTIONS: ModelCatalogEntry[] = [
  { id: "openai/gpt-4o-mini", name: "openai/gpt-4o-mini" },
  { id: "google/gemini-2.0-flash-001", name: "google/gemini-2.0-flash-001" },
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
  selected_models: DEFAULT_MODEL_OPTIONS.map((model) => model.id),
  experiment_mode: "split",
  reruns_per_persona: 1,
  notes: "",
};

const PERSONA_PREVIEW_SAMPLE_CAP = 12;

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
  const [audienceSummary, setAudienceSummary] = useState("Audience not configured yet.");
  const [productSummary, setProductSummary] = useState("Product not configured yet.");
  const [marketSummary, setMarketSummary] = useState("Market context not configured yet.");
  const [surveySummary, setSurveySummary] = useState("Survey not uploaded yet.");
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
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false);
  const [catalogModels, setCatalogModels] = useState<ModelCatalogEntry[]>(DEFAULT_MODEL_OPTIONS);
  const [catalogSource, setCatalogSource] = useState<"openrouter" | "fallback">("fallback");
  const [catalogWarning, setCatalogWarning] = useState<string | null>(null);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false);

  const loadModelCatalog = useCallback(async () => {
    setIsLoadingCatalog(true);
    try {
      const result = await getModelCatalog();
      setCatalogModels(
        result.models.length > 0 ? dedupeModels(result.models) : DEFAULT_MODEL_OPTIONS
      );
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
          setAudienceSummary("Audience not configured yet.");
          setProductSummary("Product not configured yet.");
          setMarketSummary("Market context not configured yet.");
          setSurveySummary("Survey not uploaded yet.");
          setDraft(DEFAULT_DRAFT);
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
        setAudienceSummary(buildAudienceAnchor(study.audience?.value));
        setProductSummary(buildProductAnchor(study.product?.value));
        setMarketSummary(buildMarketAnchor(study.market?.value));
        setSurveySummary(buildSurveyAnchor(study.survey));
        setDraft(nextDraft);
        setSavedSnapshot(
          hasSaved ? JSON.stringify(experimentDraftToPayload(nextDraft)) : ""
        );
        setHasSavedExperiment(hasSaved);
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
    study?.audience?.updated_at,
    study?.product?.updated_at,
    study?.market?.updated_at,
    study?.survey?.updated_at,
  ]);

  const draftPayload = useMemo(() => experimentDraftToPayload(draft), [draft]);
  const isDirty = JSON.stringify(draftPayload) !== savedSnapshot;
  const validationMessage = validateExperimentDraft(draft);
  const currentMode = EXPERIMENT_MODE_OPTIONS.find(
    (option) => option.value === draft.experiment_mode
  );
  const experimentStage = workflow?.stages?.find(
    (stage) => stage.stage_key === "experiment"
  );
  const latestPreview = study?.derived?.latest_persona_preview ?? null;
  const previewWarnings = latestPreview?.warning_messages ?? [];
  const previewPersonas = latestPreview?.personas?.slice(0, 4) ?? [];
  const previewSampleSize = Math.min(
    Math.max(draft.sample_size, 1),
    PERSONA_PREVIEW_SAMPLE_CAP
  );
  const availableModels = catalogModels.length > 0 ? catalogModels : DEFAULT_MODEL_OPTIONS;
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
    setStatus({
      tone: "warning",
      message:
        "The backend does not expose a clear experiment-plan endpoint yet. The form was reset locally; save again if you want to overwrite the persisted plan.",
    });
  }

  function handleAddModel(model: string) {
    const nextModel = model.trim();
    if (!nextModel || draft.selected_models.includes(nextModel)) {
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
    updateDraft("reruns_per_persona", Math.max(1, draft.reruns_per_persona + delta));
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

  return (
    <SectionWrapper id="experiment" scrollable contentClassName="relative">
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1.02fr)_22rem] 2xl:grid-cols-[minmax(0,1.03fr)_28rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={6}
              eyebrow="Experiment Design"
              title="Define how this study should execute."
              description="Choose the scale, model set, and comparison strategy that will govern the later simulation. This chapter now saves into canonical backend study state and also houses persona preview as a pre-run grounding check."
            />

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <ContinuityPanel compact label="Current Audience" value={audienceSummary} />
              <ContinuityPanel compact label="Current Product" value={productSummary} />
              <ContinuityPanel compact label="Current Market" value={marketSummary} />
              <ContinuityPanel compact label="Current Survey" value={surveySummary} />
            </div>

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
                {hasSavedExperiment ? "Saved in backend" : "Local draft only"}
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
                  <Field
                    label="Sample Size"
                    hint="Set the planned response count for the experiment. This defines the intended execution scale."
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
                    hint="Choose one or more model IDs. The backend now exposes a catalog endpoint with fallback starter models when live OpenRouter catalog access is unavailable."
                  >
                    <div className="rounded-[1.45rem] border border-white/8 bg-[rgba(255,255,255,0.03)] p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <BadgeChip tone={catalogSource === "openrouter" ? "cyan" : "gold"}>
                          {catalogSource === "openrouter"
                            ? "Live OpenRouter catalog"
                            : "Fallback starter catalog"}
                        </BadgeChip>
                        {catalogWarning ? <BadgeChip tone="gold">Catalog warning</BadgeChip> : null}
                      </div>

                      {catalogWarning ? (
                        <p className="mt-3 text-sm leading-6 text-app-muted">
                          {catalogWarning}
                        </p>
                      ) : null}

                      <div className="mt-4 flex flex-wrap gap-2">
                        {draft.selected_models.length > 0 ? (
                          draft.selected_models.map((model) => (
                            <button
                              key={model}
                              type="button"
                              onClick={() => handleRemoveModel(model)}
                              className="inline-flex items-center gap-2 rounded-full border border-app-cyan/20 bg-[rgba(15,216,255,0.08)] px-3 py-2 text-sm text-app-cyan transition hover:border-app-cyan/35"
                            >
                              <span>{model}</span>
                              <span className="text-app-text/70">×</span>
                            </button>
                          ))
                        ) : (
                          <span className="px-1 text-sm text-app-muted">
                            No models selected yet.
                          </span>
                        )}
                      </div>

                      <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
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
                  </Field>

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
                            onClick={() => updateDraft("experiment_mode", option.value)}
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

                  <Field
                    label="Reruns Per Persona"
                    hint="Higher reruns are most relevant for stability-oriented studies."
                  >
                    <NumericControl
                      value={draft.reruns_per_persona}
                      onChange={(value) =>
                        updateDraft("reruns_per_persona", Math.max(1, value))
                      }
                      onStep={handleRerunsStep}
                      min={1}
                    />
                  </Field>

                  <Field label="Notes" hint="Optional execution notes for the run plan.">
                    <TextAreaInput
                      value={draft.notes}
                      onChange={(value) => updateDraft("notes", value)}
                      placeholder="Add optional notes about comparison intent, budget boundaries, or execution caveats."
                      rows={4}
                    />
                  </Field>
                </div>
              </div>
            </GlassPanel>
          </div>

          <div>
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-sm leading-6",
                    status.tone === "success" &&
                      "border-app-cyan/20 bg-[rgba(15,216,255,0.08)] text-app-cyan",
                    status.tone === "warning" &&
                      "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                    status.tone === "error" &&
                      "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                    status.tone === "neutral" &&
                      "border-white/8 bg-white/[0.03] text-app-muted"
                  )}
                >
                  {status.message}
                </div>

                <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                  <Button
                    onClick={handleSavePlan}
                    disabled={isBusy}
                  >
                    {isSaving ? "Saving Experiment..." : "Save Experiment Plan"}
                  </Button>
                  <BadgeChip tone={hasSavedExperiment ? "cyan" : "gold"}>
                    {hasSavedExperiment ? "Saved state" : "Not saved yet"}
                  </BadgeChip>
                  <BadgeChip tone={isDirty ? "gold" : "neutral"}>
                    {isDirty ? "Unsaved edits" : "No new local edits"}
                  </BadgeChip>
                </div>
                {validationMessage ? (
                  <p className="mt-4 text-sm leading-6 text-app-gold">
                    {validationMessage}
                  </p>
                ) : null}
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
              </div>
            </GlassPanel>
          </div>
        </div>

        <div className="min-w-0 lg:sticky lg:top-6 lg:w-full lg:max-w-[20rem] lg:justify-self-end xl:max-w-[22rem] 2xl:max-w-[28rem]">
          <div className="space-y-5">
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="cyan">Execution Summary</BadgeChip>
                  <BadgeChip tone={hasSavedExperiment ? "cyan" : "gold"}>
                    {hasSavedExperiment ? "Saved to backend" : "Draft only"}
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

            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                  Readiness
                </div>
                <div className="mt-4 space-y-3">
                  <ReadinessRow
                    label="Current setup stack"
                    value={
                      workflow?.ready_for_persona_preview
                        ? "All setup chapters are saved, so persona preview can run against canonical study state."
                        : "At least one earlier setup chapter is still unsaved."
                    }
                    tone={workflow?.ready_for_persona_preview ? "cyan" : "gold"}
                  />
                  <ReadinessRow
                    label="Experiment stage"
                    value={
                      experimentStage?.status === "complete"
                        ? "Experiment is saved in backend study state."
                        : experimentStage?.hard_blockers?.length
                          ? experimentStage.hard_blockers.join(" • ")
                          : "Experiment can be saved once you finalize the configuration."
                    }
                    tone={experimentStage?.status === "complete" ? "cyan" : "gold"}
                  />
                  <ReadinessRow
                    label="Model catalog"
                    value={
                      catalogSource === "openrouter"
                        ? "Live OpenRouter catalog is available."
                        : catalogWarning || "Using fallback starter models."
                    }
                    tone={catalogSource === "openrouter" ? "cyan" : "gold"}
                  />
                </div>
              </div>
            </GlassPanel>

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
          </div>
        </div>
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

function experimentPayloadToDraft(
  value?: ExperimentPayload | null
): ExperimentDraft {
  const selectedModels = Array.isArray(value?.selected_models)
    ? value?.selected_models.filter((model): model is string => typeof model === "string" && model.trim().length > 0)
    : [];

  return {
    sample_size:
      typeof value?.sample_size === "number" && value.sample_size > 0
        ? value.sample_size
        : DEFAULT_DRAFT.sample_size,
    selected_models:
      selectedModels.length > 0 ? selectedModels : DEFAULT_DRAFT.selected_models,
    experiment_mode:
      value?.experiment_mode === "split" ||
      value?.experiment_mode === "mirror" ||
      value?.experiment_mode === "stability"
        ? value.experiment_mode
        : DEFAULT_DRAFT.experiment_mode,
    reruns_per_persona:
      typeof value?.reruns_per_persona === "number" && value.reruns_per_persona > 0
        ? value.reruns_per_persona
        : DEFAULT_DRAFT.reruns_per_persona,
    notes: toOptionalString(value?.notes) ?? "",
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
    notes: draft.notes.trim() || null,
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

  if (draft.selected_models.length === 0) {
    return "Select at least one model.";
  }

  if (
    (draft.experiment_mode === "split" || draft.experiment_mode === "mirror") &&
    draft.selected_models.length < 2
  ) {
    return `${draft.experiment_mode === "split" ? "Split" : "Mirror"} mode requires at least 2 selected models.`;
  }

  if (draft.experiment_mode === "stability" && draft.reruns_per_persona < 2) {
    return "Stability Sample requires reruns per persona to be at least 2.";
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

function summarizeList(values: string[], maxVisible: number) {
  const visible = values.slice(0, maxVisible);
  if (values.length <= maxVisible) {
    return visible.join(" and ");
  }
  return `${visible.join(", ")}, and more`;
}

function buildAudienceAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Audience not configured yet.";
  }

  const geography = [
    toOptionalString(value.state),
    toOptionalString(value.metro),
    toOptionalString(value.zip_code),
  ]
    .filter(Boolean)
    .join(" • ");

  const ageMin = toOptionalNumber(value.age_min);
  const ageMax = toOptionalNumber(value.age_max);
  const ageRange =
    ageMin !== null || ageMax !== null
      ? `Ages ${ageMin ?? "any"}-${ageMax ?? "any"}`
      : "All ages";

  return [geography || "All geographies", ageRange].filter(Boolean).join(" • ");
}

function buildProductAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Product not configured yet.";
  }

  return (
    [
      toOptionalString(value.product_name),
      toOptionalString(value.product_type),
      toOptionalString(value.price_range),
    ]
      .filter(Boolean)
      .join(" • ") || "Product not configured yet."
  );
}

function buildMarketAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Market context not configured yet.";
  }

  const directCompetitors = Array.isArray(value.direct_competitors)
    ? value.direct_competitors.length
    : 0;
  const substitutes = Array.isArray(value.substitutes) ? value.substitutes.length : 0;

  return [
    toOptionalString(value.category) || "Unspecified category",
    `${directCompetitors} competitors`,
    `${substitutes} substitutes`,
  ].join(" • ");
}

function buildSurveyAnchor(
  value?:
    | {
        status?: string;
        source_filename?: string | null;
        question_count?: number | null;
      }
    | null
) {
  if (!value || value.status !== "saved") {
    return "Survey not uploaded yet.";
  }

  return [
    value.source_filename || "Saved survey",
    `${value.question_count ?? 0} questions`,
  ].join(" • ");
}

function buildPersonaSnippet(persona: Record<string, unknown>) {
  const parts = [
    toOptionalString(persona.age_band),
    toOptionalString(persona.income_band),
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

function toOptionalNumber(value: unknown) {
  return typeof value === "number" ? value : null;
}

function ContinuityPanel({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-[1.35rem] border border-white/8 bg-white/[0.03]",
        compact ? "p-3.5" : "p-4"
      )}
    >
      <div className="text-[0.72rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
      <p
        className={cn(
          "mt-2 text-sm text-app-text",
          compact ? "line-clamp-3 leading-5" : "leading-6"
        )}
      >
        {value}
      </p>
    </div>
  );
}

function NumericControl({
  value,
  onChange,
  onStep,
  min,
}: {
  value: number;
  onChange: (value: number) => void;
  onStep: (delta: number) => void;
  min: number;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => onStep(-1)}
        className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan"
      >
        −
      </button>
      <input
        type="number"
        min={min}
        value={value}
        onChange={(event) => onChange(Number(event.target.value || min))}
        className="w-full rounded-2xl border border-white/8 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm text-app-text outline-none transition focus:border-app-cyan/35 focus:bg-[rgba(255,255,255,0.05)] focus:shadow-[0_0_0_4px_rgba(15,216,255,0.08)]"
      />
      <button
        type="button"
        onClick={() => onStep(1)}
        className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan"
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

function ReadinessRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "cyan" | "gold";
}) {
  return (
    <div className="rounded-[1.2rem] border border-white/6 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeChip tone={tone}>{label}</BadgeChip>
      </div>
      <p className="mt-3 text-sm leading-6 text-app-text">{value}</p>
    </div>
  );
}
