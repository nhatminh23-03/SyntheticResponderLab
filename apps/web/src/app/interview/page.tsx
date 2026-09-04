"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import {
  getInterviewModelCatalog,
  getInterviewPersonas,
  type InterviewCostEstimateAssumptions,
  type InterviewModelCatalogEntry,
  type InterviewPersona,
  type InterviewPersonaCountRange,
} from "@/lib/api";
import {
  canRunInterviewComparison,
  defaultInterviewComparisonModelIds,
  orderInterviewComparisonModelIds,
  POST_INTERVIEW_SCORE_LABEL,
  removeExpensiveComparisonModels,
  runInterviewComparison,
  toggleInterviewComparisonModel,
  type InterviewComparisonResult,
} from "@/lib/interview-comparison";
import {
  estimateInterviewRunCost,
  formatInterviewRunCostEstimate,
  formatInterviewModelOption,
  isInterviewModelSelectable,
  resetExpensiveModelSelection,
} from "@/lib/interview-models";
import { cn } from "@/lib/utils";
import { StudyProvider, useStudy } from "@/providers/study-provider";

type Turn = { role: "student" | "persona"; text: string };

const SUGGESTED = [
  "What is your first reaction to the Tahoe Mini, and what would you use it for?",
  "What would stop you from buying one?",
  "Walk me through how you'd actually decide on something like this.",
  "Who else in your household would have a say?",
];

export default function InterviewPage() {
  return (
    <StudyProvider>
      <InterviewPageContent />
    </StudyProvider>
  );
}

function InterviewPageContent() {
  const { studyId, studyBootstrapError } = useStudy();
  const [personas, setPersonas] = useState<InterviewPersona[]>([]);
  const [source, setSource] = useState("");
  const [selectedId, setSelectedId] = useState<string>("");
  const [models, setModels] = useState<InterviewModelCatalogEntry[]>([]);
  const [pricingAsOf, setPricingAsOf] = useState("");
  const [defaultModelId, setDefaultModelId] = useState("");
  const [interviewerModel, setInterviewerModel] = useState("");
  const [intervieweeModel, setIntervieweeModel] = useState("");
  const [expensiveOptIn, setExpensiveOptIn] = useState(false);
  const [personaCount, setPersonaCount] = useState(3);
  const [personaCountRange, setPersonaCountRange] = useState<InterviewPersonaCountRange>({
    minimum: 3,
    default: 3,
    maximum: 30,
  });
  const [costEstimateAssumptions, setCostEstimateAssumptions] =
    useState<InterviewCostEstimateAssumptions | null>(null);
  const [comparisonModelIds, setComparisonModelIds] = useState<string[]>([]);
  const [comparisonExpensiveOptIn, setComparisonExpensiveOptIn] = useState(false);
  const [comparisonQuestion, setComparisonQuestion] = useState(SUGGESTED[0]);
  const [comparedQuestion, setComparedQuestion] = useState("");
  const [comparisonResults, setComparisonResults] = useState<InterviewComparisonResult[]>([]);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [question, setQuestion] = useState(SUGGESTED[0]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const transcriptEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    Promise.all([getInterviewPersonas(), getInterviewModelCatalog()])
      .then(([personaData, modelData]) => {
        setPersonas(personaData.personas);
        setSource(personaData.source);
        setSelectedId(personaData.personas[0]?.persona_id ?? "");
        setModels(modelData.models);
        setPricingAsOf(modelData.pricingAsOf);
        setDefaultModelId(modelData.defaultModelId);
        setInterviewerModel(modelData.defaultModelId);
        setIntervieweeModel(modelData.defaultModelId);
        setComparisonModelIds(defaultInterviewComparisonModelIds(modelData.models));
        setPersonaCountRange(modelData.personaCount);
        setPersonaCount(modelData.personaCount.default);
        setCostEstimateAssumptions(modelData.costEstimate);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, loading]);

  const persona = personas.find((entry) => entry.persona_id === selectedId);
  const interviewerModelEntry = models.find((entry) => entry.id === interviewerModel);
  const intervieweeModelEntry = models.find((entry) => entry.id === intervieweeModel);
  const preflightCostEstimate =
    interviewerModelEntry && intervieweeModelEntry
      ? estimateInterviewRunCost(personaCount, interviewerModelEntry, intervieweeModelEntry)
      : null;
  const modelsLocked = turns.length > 0 || loading;

  function selectPersona(id: string) {
    setSelectedId(id);
    setTurns([]);
    setSystemPrompt("");
    setError("");
    setExpensiveOptIn(false);
    setInterviewerModel(defaultModelId);
    setIntervieweeModel(defaultModelId);
    setComparisonExpensiveOptIn(false);
    setComparisonModelIds(defaultInterviewComparisonModelIds(models));
    setComparedQuestion("");
    setComparisonResults([]);
  }

  function setExpensiveModelsForRun(enabled: boolean) {
    setExpensiveOptIn(enabled);
    if (!enabled) {
      setInterviewerModel((selected) =>
        resetExpensiveModelSelection(models, selected, defaultModelId)
      );
      setIntervieweeModel((selected) =>
        resetExpensiveModelSelection(models, selected, defaultModelId)
      );
    }
  }

  function setExpensiveComparisonModelsForRun(enabled: boolean) {
    setComparisonExpensiveOptIn(enabled);
    if (!enabled) {
      setComparisonModelIds((selected) =>
        removeExpensiveComparisonModels(models, selected)
      );
    }
  }

  async function compareModels() {
    const asked = comparisonQuestion.trim();
    const orderedModelIds = orderInterviewComparisonModelIds(models, comparisonModelIds);
    if (
      !asked ||
      loading ||
      comparisonLoading ||
      !studyId ||
      !persona ||
      !canRunInterviewComparison(orderedModelIds)
    ) {
      return;
    }

    setComparisonLoading(true);
    setComparedQuestion(asked);
    setComparisonResults([]);

    const results = await runInterviewComparison({
      studyId,
      personaId: persona.persona_id,
      question: asked,
      modelIds: orderedModelIds,
      allowExpensiveModels: comparisonExpensiveOptIn,
    });
    setComparisonResults(results);
    setComparisonLoading(false);
  }

  async function ask() {
    const asked = question.trim();
    if (!asked || loading || !persona || !interviewerModel || !intervieweeModel) return;

    setLoading(true);
    setError("");
    setTurns((previous) => [...previous, { role: "student", text: asked }]);
    setQuestion("");

    try {
      const response = await fetch("/api/demo-interview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // turns is the pre-append render value, i.e. history without the question being asked.
        body: JSON.stringify({
          personaId: selectedId,
          question: asked,
          history: turns,
          interviewerModel,
          intervieweeModel,
          allowExpensiveModels: expensiveOptIn,
        }),
      });
      const data = await response.json();
      if (data.systemPrompt) setSystemPrompt(data.systemPrompt);
      if (!response.ok) {
        setError(data.error ?? "Request failed.");
        return;
      }
      setTurns((previous) => [...previous, { role: "persona", text: data.answer }]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-svh px-4 py-10 sm:px-6 lg:px-12">
      <div className="mx-auto w-full max-w-[88rem]">
        <div className="mb-4 flex flex-wrap items-center gap-2.5 sm:gap-3">
          <BadgeChip tone="gold">Interview</BadgeChip>
          <BadgeChip>Student interviews a persona</BadgeChip>
          {source ? <BadgeChip>{source}</BadgeChip> : null}
        </div>
        <h1 className="font-display text-[2.45rem] font-medium leading-[0.95] tracking-[-0.05em] text-app-text sm:text-[2.9rem] lg:text-[3.35rem]">
          Interview a persona
        </h1>
        <p className="mt-4 max-w-2xl text-[0.98rem] leading-7 text-app-muted sm:text-base">
          Each persona below is one real household drawn from US Census microdata. Pick one, ask a
          question, and it answers in character from its own record. Nothing from the 600 real survey
          responses reaches these prompts.
        </p>

        <div className="mt-8 grid gap-5 lg:grid-cols-[22rem_minmax(0,1fr)]">
          <GlassPanel className="p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
              Personas ({personas.length})
            </p>
            <div className="fine-scrollbar mt-4 flex max-h-[26rem] flex-col gap-2 overflow-y-auto pr-1">
              {personas.map((entry) => (
                <button
                  key={entry.persona_id}
                  type="button"
                  onClick={() => selectPersona(entry.persona_id)}
                  disabled={comparisonLoading}
                  className={cn(
                    "rounded-xl border px-3.5 py-2.5 text-left transition duration-200 disabled:cursor-not-allowed disabled:opacity-60",
                    entry.persona_id === selectedId
                      ? "border-app-borderStrong text-app-text [background:var(--button-secondary-bg-hover)]"
                      : "border-app-border text-app-muted hover:border-app-borderStrong hover:text-app-text"
                  )}
                >
                  <span className="block text-sm font-semibold">{entry.persona_id}</span>
                  <span className="mt-0.5 block text-xs leading-5">
                    {entry.census_profile.split(".").slice(0, 2).join(".") || "—"}
                  </span>
                </button>
              ))}
            </div>
          </GlassPanel>

          <div className="flex flex-col gap-5">
            <GlassPanel className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
                    Models for this run
                  </p>
                  <p className="mt-2 text-xs leading-5 text-app-muted">
                    Selections lock after the first question. The interviewer choice is ready for
                    AI-led runs; this student-led interview uses the interviewee model now.
                  </p>
                </div>
                {pricingAsOf ? <BadgeChip>prices checked {pricingAsOf}</BadgeChip> : null}
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">
                  Interviewer model
                  <select
                    aria-label="Interviewer model"
                    value={interviewerModel}
                    onChange={(event) => setInterviewerModel(event.target.value)}
                    disabled={modelsLocked || models.length === 0}
                    className="mt-2 w-full rounded-xl border border-app-border bg-transparent px-3 py-3 text-sm normal-case tracking-normal text-app-text outline-none transition focus:border-app-borderStrong disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {models.map((model) => (
                      <option
                        key={model.id}
                        value={model.id}
                        disabled={!isInterviewModelSelectable(model, expensiveOptIn)}
                      >
                        {formatInterviewModelOption(model)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">
                  Interviewee model
                  <select
                    aria-label="Interviewee model"
                    value={intervieweeModel}
                    onChange={(event) => setIntervieweeModel(event.target.value)}
                    disabled={modelsLocked || models.length === 0}
                    className="mt-2 w-full rounded-xl border border-app-border bg-transparent px-3 py-3 text-sm normal-case tracking-normal text-app-text outline-none transition focus:border-app-borderStrong disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {models.map((model) => (
                      <option
                        key={model.id}
                        value={model.id}
                        disabled={!isInterviewModelSelectable(model, expensiveOptIn)}
                      >
                        {formatInterviewModelOption(model)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="mt-4 flex items-start gap-2 text-xs leading-5 text-app-muted">
                <input
                  type="checkbox"
                  checked={expensiveOptIn}
                  onChange={(event) => setExpensiveModelsForRun(event.target.checked)}
                  disabled={modelsLocked}
                  className="mt-0.5 size-4 accent-[var(--color-gold)] disabled:cursor-not-allowed"
                />
                Enable expensive models for this run. This opt-in resets when you start over with
                another persona.
              </label>

              <div className="mt-5 border-t border-app-border pt-5">
                <div className="flex items-center justify-between gap-4">
                  <label
                    htmlFor="ai-interview-persona-count"
                    className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted"
                  >
                    AI-to-AI batch size
                  </label>
                  <span className="text-sm font-semibold tabular-nums text-app-text">
                    {personaCount} personas
                  </span>
                </div>
                <input
                  id="ai-interview-persona-count"
                  aria-label="Personas in AI-to-AI run"
                  type="range"
                  min={personaCountRange.minimum}
                  max={personaCountRange.maximum}
                  step={1}
                  value={personaCount}
                  onChange={(event) => setPersonaCount(Number(event.target.value))}
                  disabled={modelsLocked || models.length === 0}
                  className="mt-3 w-full accent-[var(--color-gold)] disabled:cursor-not-allowed disabled:opacity-60"
                />
                <div className="mt-1 flex justify-between text-[0.68rem] tabular-nums text-app-muted">
                  <span>{personaCountRange.minimum} minimum</span>
                  <span>{personaCountRange.maximum} maximum</span>
                </div>

                <div className="mt-4 rounded-xl border border-app-border px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">
                    Pre-flight estimate
                  </p>
                  <p className="mt-1 text-lg font-semibold tabular-nums text-app-text">
                    {preflightCostEstimate == null
                      ? "Calculating…"
                      : `This run will cost about ${formatInterviewRunCostEstimate(preflightCostEstimate)}`}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-app-muted">
                    For {personaCount} personas with both selected models
                    {costEstimateAssumptions
                      ? `, allowing ${costEstimateAssumptions.prompt_tokens_per_model_persona.toLocaleString()} input and ${costEstimateAssumptions.completion_tokens_per_model_persona.toLocaleString()} output tokens per model/persona.`
                      : "."}
                  </p>
                  <p className="mt-1 text-[0.68rem] leading-5 text-app-muted">
                    Planning estimate from catalog prices; provider-measured cost may differ.
                  </p>
                </div>
              </div>
            </GlassPanel>

            {persona ? (
              <GlassPanel className="p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <BadgeChip tone="gold">{persona.persona_id}</BadgeChip>
                  <BadgeChip>{persona.age_bucket}</BadgeChip>
                  <BadgeChip>{persona.income_bucket}</BadgeChip>
                  <BadgeChip>{persona.ownership}</BadgeChip>
                  <BadgeChip>{persona.home_type}</BadgeChip>
                </div>
                <p className="mt-4 text-[0.95rem] leading-7 text-app-text">{persona.census_profile}</p>
                {persona.lifestyle_tags.length ? (
                  <p className="mt-3 text-xs leading-6 text-app-muted">
                    {persona.lifestyle_tags.join(" · ")}
                  </p>
                ) : null}
              </GlassPanel>
            ) : null}

            <GlassPanel className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
                    Compare model answers
                  </p>
                  <h2 className="mt-2 font-display text-2xl font-medium tracking-[-0.035em] text-app-text">
                    Same persona. Same question. Different models.
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-app-muted">
                    Hold the inputs constant and compare at least two answers side by side. Model
                    prices stay visible so differences in specificity, tone, and reasoning can be
                    weighed against cost.
                  </p>
                </div>
                <BadgeChip tone="cyan">Controlled comparison</BadgeChip>
              </div>

              <fieldset className="mt-5" disabled={comparisonLoading}>
                <legend className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">
                  Models to compare ({comparisonModelIds.length} selected)
                </legend>
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  {models.map((model) => {
                    const expensiveLocked =
                      model.tier === "expensive" && !comparisonExpensiveOptIn;
                    return (
                      <label
                        key={model.id}
                        className={cn(
                          "flex items-start gap-3 rounded-xl border border-app-border px-3.5 py-3 transition",
                          expensiveLocked
                            ? "cursor-not-allowed opacity-50"
                            : "cursor-pointer hover:border-app-borderStrong [background:var(--button-secondary-bg)]"
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={comparisonModelIds.includes(model.id)}
                          onChange={(event) =>
                            setComparisonModelIds((selected) =>
                              toggleInterviewComparisonModel(
                                selected,
                                model.id,
                                event.target.checked
                              )
                            )
                          }
                          disabled={expensiveLocked}
                          className="mt-0.5 size-4 shrink-0 accent-[var(--color-gold)]"
                        />
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-app-text">
                            {model.name}
                          </span>
                          <span className="mt-0.5 block text-xs leading-5 text-app-muted">
                            {model.tier} · ${model.prompt_price_per_million.toFixed(2)} in / $
                            {model.completion_price_per_million.toFixed(2)} out per 1M tokens
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-app-muted">
                <input
                  type="checkbox"
                  checked={comparisonExpensiveOptIn}
                  onChange={(event) =>
                    setExpensiveComparisonModelsForRun(event.target.checked)
                  }
                  disabled={comparisonLoading}
                  className="mt-0.5 size-4 accent-[var(--color-gold)] disabled:cursor-not-allowed"
                />
                Enable expensive models for this comparison. Add one above to compare the price
                extremes; the opt-in resets when you choose another persona.
              </label>

              {!canRunInterviewComparison(comparisonModelIds) ? (
                <p className="mt-3 text-xs leading-5 text-app-muted">
                  Select at least two models to make a comparison.
                </p>
              ) : null}

              <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                <input
                  aria-label="Question for model comparison"
                  value={comparisonQuestion}
                  onChange={(event) => setComparisonQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") compareModels();
                  }}
                  disabled={comparisonLoading}
                  placeholder="Ask every model the same question…"
                  className="flex-1 rounded-xl border border-app-border bg-transparent px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted focus:border-app-borderStrong disabled:cursor-not-allowed disabled:opacity-60"
                />
                <Button
                  onClick={compareModels}
                  disabled={
                    loading ||
                    comparisonLoading ||
                    !comparisonQuestion.trim() ||
                    !studyId ||
                    !persona ||
                    !canRunInterviewComparison(comparisonModelIds)
                  }
                >
                  {comparisonLoading
                    ? `Comparing ${comparisonModelIds.length} models…`
                    : `Compare ${comparisonModelIds.length} models`}
                </Button>
              </div>

              {studyBootstrapError ? (
                <p className="mt-3 text-xs leading-5 text-app-muted">
                  Model comparison is unavailable: {studyBootstrapError}
                </p>
              ) : null}

              {comparisonLoading ? (
                <p className="mt-5 text-sm text-app-muted" aria-live="polite">
                  Asking each model independently…
                </p>
              ) : null}

              {comparisonResults.length > 0 ? (
                <section className="mt-6 border-t border-app-border pt-5" aria-live="polite">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">
                        Question held constant
                      </p>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-app-text">
                        “{comparedQuestion}”
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <BadgeChip>{persona?.persona_id}</BadgeChip>
                      <BadgeChip>{comparisonResults.length} models</BadgeChip>
                    </div>
                  </div>

                  <div className="fine-scrollbar mt-4 grid auto-cols-[minmax(18rem,1fr)] grid-flow-col gap-4 overflow-x-auto pb-2">
                    {comparisonResults.map((result) => {
                      const model = models.find((entry) => entry.id === result.modelId);
                      return (
                        <article
                          key={result.modelId}
                          className="flex min-h-64 flex-col rounded-2xl border border-app-border p-4 [background:var(--button-secondary-bg)]"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <h3 className="text-sm font-semibold text-app-text">
                                {model?.name ?? result.modelId}
                              </h3>
                              {model ? (
                                <p className="mt-1 text-[0.68rem] leading-5 text-app-muted">
                                  ${model.prompt_price_per_million.toFixed(2)} in / $
                                  {model.completion_price_per_million.toFixed(2)} out per 1M tokens
                                </p>
                              ) : null}
                            </div>
                            {model ? (
                              <BadgeChip tone={model.tier === "expensive" ? "gold" : "neutral"}>
                                {model.tier}
                              </BadgeChip>
                            ) : null}
                          </div>
                          <div className="mt-4 border-t border-app-border pt-4">
                            {result.answer ? (
                              <p className="whitespace-pre-wrap text-sm leading-7 text-app-text">
                                {result.answer}
                              </p>
                            ) : (
                              <p className="text-sm leading-6 text-app-muted">
                                {result.error ?? "No answer returned."}
                              </p>
                            )}
                          </div>
                          {result.postInterviewScore ? (
                            <div className="mt-auto border-t border-app-border pt-4">
                              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-app-muted">
                                {POST_INTERVIEW_SCORE_LABEL}
                              </p>
                              <div className="mt-2 flex flex-wrap gap-2">
                                <BadgeChip>
                                  fit tier: {result.postInterviewScore.fitTier}
                                </BadgeChip>
                                <BadgeChip>
                                  emotion: {result.postInterviewScore.emotionalClassification}
                                </BadgeChip>
                              </div>
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                </section>
              ) : null}
            </GlassPanel>

            <GlassPanel className="flex min-h-[22rem] flex-col p-5">
              <div className="fine-scrollbar flex-1 space-y-4 overflow-y-auto pr-1">
                {turns.length === 0 && !loading ? (
                  <p className="text-sm leading-7 text-app-muted">
                    Ask the first question to start the interview.
                  </p>
                ) : null}
                <AnimatePresence initial={false}>
                  {turns.map((turn, index) => (
                    <motion.div
                      key={`${index}-${turn.role}`}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={cn("max-w-[46rem]", turn.role === "student" && "ml-auto text-right")}
                    >
                      <p className="mb-1 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-app-muted">
                        {turn.role === "student" ? "You" : persona?.persona_id}
                      </p>
                      <p
                        className={cn(
                          "inline-block rounded-2xl border border-app-border px-4 py-3 text-[0.95rem] leading-7 text-app-text",
                          turn.role === "student"
                            ? "[background:var(--button-secondary-bg)]"
                            : "[background:var(--glass-panel-bg)]"
                        )}
                      >
                        {turn.text}
                      </p>
                    </motion.div>
                  ))}
                </AnimatePresence>
                {loading ? <p className="text-sm text-app-muted">thinking…</p> : null}
                <div ref={transcriptEnd} />
              </div>

              {error ? (
                <p className="mt-3 rounded-xl border border-app-border px-4 py-3 text-sm leading-6 text-app-text">
                  {error}
                </p>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                {SUGGESTED.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setQuestion(suggestion)}
                    className="rounded-full border border-app-border px-3 py-1.5 text-xs text-app-muted transition hover:border-app-borderStrong hover:text-app-text"
                  >
                    {suggestion.length > 52 ? `${suggestion.slice(0, 52)}…` : suggestion}
                  </button>
                ))}
              </div>

              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <input
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") ask();
                  }}
                  placeholder="Ask a follow-up…"
                  className="flex-1 rounded-xl border border-app-border bg-transparent px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted focus:border-app-borderStrong"
                />
                <Button
                  onClick={ask}
                  disabled={
                    loading ||
                    !question.trim() ||
                    !persona ||
                    !interviewerModel ||
                    !intervieweeModel
                  }
                >
                  {loading ? "Asking…" : "Ask"}
                </Button>
              </div>
            </GlassPanel>

            {systemPrompt ? (
              <GlassPanel className="p-5">
                <button
                  type="button"
                  onClick={() => setShowPrompt((value) => !value)}
                  className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted transition hover:text-app-text"
                >
                  {showPrompt ? "Hide" : "Show"} the prompt built from this record
                </button>
                {showPrompt ? (
                  <pre className="fine-scrollbar mt-4 max-h-72 overflow-auto whitespace-pre-wrap text-xs leading-6 text-app-muted">
                    {systemPrompt}
                  </pre>
                ) : null}
              </GlassPanel>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}
