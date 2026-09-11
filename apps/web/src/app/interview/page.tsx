"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import {
  getInterviewModelCatalog,
  getInterviewPersonas,
  getInterviewTranscriptExport,
  InterviewChatApiError,
  sendInterviewChatMessage,
  type InterviewCostEstimateAssumptions,
  type InterviewModelCatalogEntry,
  type InterviewPersona,
  type InterviewPersonaCountRange,
  type InterviewTranscriptExportFormat,
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

import { batchExport } from "@/lib/interview-batch-export";
import { InterviewOperationError, interviewOperation, type Batch, type RegeneratedAnswer } from "@/lib/standalone-interview";

type Turn = { role: "student" | "persona"; text: string; answerId?: string; version?: number };

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
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);
  const [loading, setLoading] = useState(false);
  const [exportingFormat, setExportingFormat] =
    useState<InterviewTranscriptExportFormat | null>(null);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState<Batch | null>(null);
  const [batchHistory, setBatchHistory] = useState<Batch[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [pausing, setPausing] = useState(false);
  const regenerationRetries = useRef<Record<string, number>>({});
  const [regenerating, setRegenerating] = useState(false);
  const [regenerationCost, setRegenerationCost] = useState<string | null>(null);
  const activity = useRef(false);
  const pauseBatch = useRef(false);
  const generation = useRef(0);
  const batchRequest = useRef<{ request_id: string; persona_count: number; interviewer_model: string; interviewee_model: string; allow_expensive_models: boolean } | null>(null);
  const busy = loading || comparisonLoading || batchLoading || regenerating;
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
  const modelsLocked = turns.length > 0 || busy;

  function selectPersona(id: string) {
    if (activity.current) return;
    generation.current += 1;
    setSelectedId(id);
    setTurns([]);
    setSessionId(null);
    setSystemPrompt("");
    setError("");
    setExpensiveOptIn(false);
    setInterviewerModel(defaultModelId);
    setIntervieweeModel(defaultModelId);
    setComparisonExpensiveOptIn(false);
    setComparisonModelIds(defaultInterviewComparisonModelIds(models));
    setComparedQuestion("");
    setComparisonResults([]);
    setRegenerationCost(null);
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
      activity.current ||
      busy ||
      comparisonLoading ||
      !studyId ||
      !persona ||
      !canRunInterviewComparison(orderedModelIds)
    ) {
      return;
    }

    activity.current = true;
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
    activity.current = false;
  }

  async function ask() {
    const asked = question.trim();
    if (
      !asked ||
      activity.current ||
      busy ||
      !studyId ||
      !persona ||
      !interviewerModel ||
      !intervieweeModel
    ) {
      return;
    }

    activity.current = true;
    setLoading(true);
    setError("");
    setTurns((previous) => [...previous, { role: "student", text: asked }]);
    setQuestion("");

    try {
      const response = await sendInterviewChatMessage(studyId, {
        persona_id: selectedId,
        prompt: asked,
        // turns is the pre-append render value, i.e. history without the question being asked.
        messages: turns.map((turn) => ({
          role: turn.role === "persona" ? "assistant" : "user",
          content: turn.text,
        })),
        model: intervieweeModel,
        session_id: sessionId,
        standalone: true,
        allow_expensive_models: expensiveOptIn,
      });
      setSessionId(response.session_id);
      if (response.system_prompt) setSystemPrompt(response.system_prompt);
      setTurns((previous) => [...previous, { role: "persona", text: response.reply, answerId: response.answer_id, version: response.version ?? 0 }]);
    } catch (err) {
      const committed = err instanceof InterviewChatApiError ? err.committedAnswer : null;
      if (committed) {
        setSessionId(committed.session_id);
        setTurns(previous => [...previous, { role: "persona", text: committed.reply, answerId: committed.answer_id, version: committed.version ?? 0 }]);
      } else {
        setTurns(turns);
        setQuestion(asked);
      }
      if (err instanceof InterviewChatApiError && err.systemPrompt) {
        setSystemPrompt(err.systemPrompt);
      }
      setError((err as Error).message);
    } finally {
      setLoading(false);
      activity.current = false;
    }
  }

  useEffect(() => {
    if (!studyId) return;
    const saved = localStorage.getItem(`interview-batch:${studyId}`);
    const savedRequest = localStorage.getItem(`interview-batch-request:${studyId}`);
    if (savedRequest) {
      try { batchRequest.current = JSON.parse(savedRequest); } catch { /* Ignore invalid local recovery data. */ }
    }
    let active = true;
    interviewOperation<{ batches: Batch[] }>(studyId, "batches")
      .then(({ batches }) => {
        if (active) setBatchHistory(previous => [
          ...previous, ...batches.filter(item => !previous.some(saved => saved.job_id === item.job_id)),
        ]);
      })
      .catch((err: Error) => { if (active) setError(err.message); });
    if (saved) interviewOperation<{ batch: Batch }>(studyId, `batches/${encodeURIComponent(saved)}`)
      .then(({ batch: recovered }) => { if (active) setBatch(previous => previous ?? recovered); })
      .catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; pauseBatch.current = true; generation.current += 1; };
  }, [studyId]);

  async function runBatch(resume = false) {
    if (!studyId || activity.current || !interviewerModel || !intervieweeModel) return;
    activity.current = true;
    pauseBatch.current = false;
    setPausing(false);
    setBatchLoading(true);
    setError("");
    try {
      let current: Batch;
      if (resume && batch) {
        current = (await interviewOperation<{ batch: Batch }>(studyId, `batches/${batch.job_id}`)).batch;
      } else {
        const request = batchRequest.current ?? {
          request_id: crypto.randomUUID(), persona_count: personaCount,
          interviewer_model: interviewerModel, interviewee_model: intervieweeModel,
          allow_expensive_models: expensiveOptIn,
        };
        batchRequest.current = request;
        localStorage.setItem(`interview-batch-request:${studyId}`, JSON.stringify(request));
        try {
          current = (await interviewOperation<{ batch: Batch }>(studyId, "batches", request)).batch;
        } catch (err) {
          // A definite rejection is safe to discard; an ambiguous network result keeps its ID.
          if (err instanceof InterviewOperationError && err.status >= 400 && err.status < 500) {
            batchRequest.current = null;
            localStorage.removeItem(`interview-batch-request:${studyId}`);
          }
          throw err;
        }
        localStorage.setItem(`interview-batch:${studyId}`, current.job_id);
        localStorage.removeItem(`interview-batch-request:${studyId}`);
        batchRequest.current = null;
      }
      setBatch(current);
      const started = current;
      setBatchHistory(previous => [started, ...previous.filter(item => item.job_id !== started.job_id)]);
      do {
        if (pauseBatch.current || current.status === "completed" || current.status === "budget_stopped") break;
        current = (await interviewOperation<{ batch: Batch }>(studyId, `batches/${current.job_id}/advance`, { revision: current.revision, retry: resume && current.status === "failed" })).batch;
        setBatch(current);
        const updated = current;
        setBatchHistory(previous => previous.map(item => item.job_id === updated.job_id ? updated : item));
      } while (current.status === "running");
    } catch (err) {
      setError(`${(err as Error).message} Saved batch progress can be recovered with Resume batch.`);
    } finally {
      setBatchLoading(false);
      activity.current = false;
    }
  }

  async function regenerate(answerId: string, version: number, comparison: boolean) {
    if (!studyId || activity.current) return;
    activity.current = true;
    setRegenerating(true);
    setError("");
    const originalGeneration = generation.current;
    try {
      const { answer } = await interviewOperation<{ answer: RegeneratedAnswer }>(studyId,
        `answers/${encodeURIComponent(answerId)}/regenerate`, {
          version: regenerationRetries.current[answerId] ?? version, retry: answerId in regenerationRetries.current, allow_expensive_models: comparison ? comparisonExpensiveOptIn : expensiveOptIn,
        });
      if (originalGeneration !== generation.current) return;
      delete regenerationRetries.current[answerId];
      if (comparison) {
        setComparisonResults(previous => previous.map(result => result.answerId === answerId ? {
          ...result, answer: answer.reply, version: answer.version,
          postInterviewScore: { fitTier: answer.post_interview_score.fit_tier, emotionalClassification: answer.post_interview_score.emotional_classification },
        } : result));
      } else {
        setTurns(previous => previous.map(turn => turn.answerId === answerId ? { ...turn, text: answer.reply, version: answer.version } : turn));
      }
      setRegenerationCost(answer.session_usage.cost_usd);
      if (answer.budget_stop) setError(answer.budget_stop.message);
    } catch (err) {
      if (originalGeneration !== generation.current) return;
      if (err instanceof InterviewOperationError && err.details?.answer_id === answerId &&
          err.details.retry_required && typeof err.details.version === "number") {
        regenerationRetries.current[answerId] = err.details.version;
      }
      setError((err as Error).message);
    } finally {
      setRegenerating(false);
      activity.current = false;
    }
  }

  async function exportTranscript(format: InterviewTranscriptExportFormat) {
    if (!studyId || !persona || turns.length === 0 || exportingFormat) return;

    setExportingFormat(format);
    setError("");
    try {
      const exported = await getInterviewTranscriptExport(
        studyId,
        {
          persona_id: persona.persona_id,
          interviewee_model: intervieweeModel,
          turns,
        },
        format
      );
      const downloadUrl = URL.createObjectURL(exported.blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = exported.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setExportingFormat(null);
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

        <a
          href="/prerecorded-interviews.html"
          className="mt-5 inline-flex items-center gap-2 rounded-xl border border-app-border px-4 py-2.5 text-sm font-semibold text-app-text transition hover:border-[var(--color-gold)] hover:text-[var(--color-gold)]"
        >
          Browse pre-recorded interviews
          <span aria-hidden="true">&rarr;</span>
        </a>
        <p className="mt-2 max-w-2xl text-xs leading-5 text-app-muted">
          Complete eight-turn interviews for all 30 personas on both of Dr. Lin&rsquo;s recommended
          models, recorded ahead of time. Replaying one costs nothing.
        </p>

        {regenerationCost ? <p className="mt-3 text-sm" role="status">Measured session cost after regeneration: ${Number(regenerationCost).toFixed(6)}</p> : null}
        {regenerating ? <p role="status">Regenerating answer…</p> : null}
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
                  disabled={busy}
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
                    Selections lock after the first question. The interviewer model conducts
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

            <GlassPanel className="p-5" aria-label="AI-to-AI batch results">
              <div className="flex flex-wrap gap-2">
                <Button disabled={busy || !studyId || !interviewerModel || !intervieweeModel} onClick={() => runBatch()}>
                  Run AI-to-AI batch ({personaCount} personas)
                </Button>
                {batch && (batch.status === "running" || batch.status === "failed") ? (
                  <Button variant="secondary" disabled={busy} onClick={() => runBatch(true)}>Resume batch</Button>
                ) : null}
                {batchLoading ? <Button variant="secondary" disabled={pausing} onClick={() => { pauseBatch.current = true; setPausing(true); }}>Pause after this call</Button> : null}
              </div>
              <p className="mt-2 text-xs text-app-muted">Eight adaptive questions per persona using the fixed household set and Tahoe Mini research brief. Cached interviews replay free.</p>
              {batchHistory.length > 0 ? <label className="mt-4 block">Saved batches
                <select aria-label="Saved batches" disabled={busy} value={batch?.job_id ?? ""}
                  onChange={event => {
                    const selected = batchHistory.find(item => item.job_id === event.target.value);
                    if (selected && studyId) {
                      setBatch(selected);
                      localStorage.setItem(`interview-batch:${studyId}`, selected.job_id);
                    }
                  }}>
                  <option value="" disabled>Select a saved batch</option>
                  {batchHistory.map(item => <option key={item.job_id} value={item.job_id}>
                    {item.job_id} · {item.status} · {item.completed_personas}/{item.persona_count} personas · ${Number(item.session_usage.cost_usd).toFixed(6)}
                  </option>)}
                </select>
              </label> : null}
              {batch ? <div aria-live="polite" className="mt-4 space-y-3">
                <p>{batch.status === "budget_stopped" ? "Budget stop" : batch.status === "running" ? (batchLoading ? (pausing ? "Pausing after current call…" : "running") : error ? "Execution unconfirmed — Resume to recover" : "Paused — select Resume batch to continue") : batch.status}: {batch.completed_personas}/{batch.persona_count} personas complete · {batch.transcripts.reduce((total, transcript) => total + transcript.messages.length, 0)}/{batch.persona_count * batch.turn_limit * 2} calls resolved</p>
                <p>Measured cost: ${Number(batch.session_usage.cost_usd).toFixed(6)} · Estimate at start: ${Number(batch.estimated_cost_usd).toFixed(4)}</p>
                <p className="text-xs text-app-muted">Interviewer: {batch.interviewer_model} · Interviewee: {batch.interviewee_model}</p>
                <div className="flex gap-2">{(["csv", "md"] as const).map(format => <Button key={format} variant="secondary" onClick={() => {
                  const exported = batchExport(batch, format);
                  const url = URL.createObjectURL(exported.blob);
                  const link = document.createElement("a");
                  link.href = url; link.download = exported.filename;
                  document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
                }}>Download batch {format === "csv" ? "CSV" : "Markdown"}</Button>)}</div>
                {batch.error ? <p role="alert">{batch.error.details?.scope ? `${batch.error.details.scope} cap: ` : ""}{batch.error.message}</p> : null}
                {batch.transcripts.map(transcript => <details key={transcript.persona_id} className="rounded-xl border border-app-border p-3">
                  <summary>{transcript.persona_id} · {Math.floor(transcript.messages.length / 2)}/{batch.turn_limit} answers</summary>
                  {transcript.messages.map((message, index) => <p key={index} className="mt-3 whitespace-pre-wrap text-sm leading-6"><strong>{message.role === "user" ? "Interviewer" : transcript.persona_id}: </strong>{message.content}</p>)}
                </details>)}
              </div> : batchLoading ? <p role="status">Starting batch…</p> : null}
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

              <fieldset className="mt-5" disabled={busy}>
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
                  disabled={busy}
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
                  disabled={busy}
                  placeholder="Ask every model the same question…"
                  className="flex-1 rounded-xl border border-app-border bg-transparent px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted focus:border-app-borderStrong disabled:cursor-not-allowed disabled:opacity-60"
                />
                <Button
                  onClick={compareModels}
                  disabled={
                    busy ||
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
                          {result.answerId && result.answer ? <Button variant="secondary" disabled={busy} onClick={() => regenerate(result.answerId!, result.version ?? 0, true)}>Regenerate answer (paid)</Button> : null}
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
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
                    Session transcript
                  </p>
                  <p className="mt-1 text-xs leading-5 text-app-muted">
                    Download your interview as CSV or Markdown to submit it.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => exportTranscript("csv")}
                    disabled={turns.length === 0 || busy || exportingFormat !== null || !studyId}
                  >
                    {exportingFormat === "csv" ? "Exporting…" : "Export CSV"}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => exportTranscript("markdown")}
                    disabled={turns.length === 0 || busy || exportingFormat !== null || !studyId}
                  >
                    {exportingFormat === "markdown" ? "Exporting…" : "Export Markdown"}
                  </Button>
                </div>
              </div>

              <div className="fine-scrollbar mt-4 flex-1 space-y-4 overflow-y-auto pr-1">
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
                      {turn.answerId && index === turns.length - 1 ? <Button variant="secondary" disabled={busy} onClick={() => regenerate(turn.answerId!, turn.version ?? 0, false)}>Regenerate answer (paid)</Button> : null}
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
                    busy ||
                    !question.trim() ||
                    !studyId ||
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
