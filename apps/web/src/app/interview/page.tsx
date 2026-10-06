"use client";

import { DemoScreens, DemoNotice, useDemoActivity } from "@/components/demo/demo-mode";
import { isDemoMode, useDemoMode } from "@/lib/demo-mode";

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
import { WorkflowNav } from "@/components/ui/workflow-nav";
import { StudyProvider, useStudy } from "@/providers/study-provider";
import { ThemeProvider } from "@/providers/theme-provider";

import { batchExport, REFLECTION_PROMPTS, type StudentMemo } from "@/lib/interview-batch-export";
import { InterviewOperationError, interviewOperation, type Batch, type RegeneratedAnswer } from "@/lib/standalone-interview";

type Themes = {
  from_run_id: string; revision: string; eligible: boolean; available: boolean; stale: boolean;
  estimated_cost_usd: string; model: string; message: string; session_usage?: { cost_usd: string };
  saved: { revision: string; attempt: number; message?: string; budget_stop?: string;
    themes: { label: string; synthesis: string; representative_quote: string; quote_persona_id: string; sentiment: string }[] | null;
    surprise?: { summary: string; quote: string; quote_persona_id: string } | null;
    answer_options?: { text: string; quote_persona_id: string }[] | null } | null;
  emotion?: { scored: number; interviewed: number; answers: number; label: string;
    counts: Record<string, number>;
    personas: { persona_id: string | null; fit_tier: string; answers: number;
      classified: number; positive: number; neutral: number; negative: number }[] };
};

type Turn = { role: "student" | "persona"; text: string; answerId?: string; version?: number };

const SUGGESTED = [
  "What is your first reaction to the Tahoe Mini, and what would you use it for?",
  "What would stop you from buying one?",
  "Walk me through how you'd actually decide on something like this.",
  "Who else in your household would have a say?",
];

const MEMO_STORE = "interview-memos";
const EMPTY_MEMO: StudentMemo = { themes: "", surprise: "", options: ["", "", ""] };

/** Anything in the store was written by an older build, another tab or a hand edit. */
function readMemos(raw: string | null): Record<string, StudentMemo> {
  const parsed = raw ? JSON.parse(raw) : null;
  if (!parsed || typeof parsed !== "object") return {};
  return Object.fromEntries(Object.entries(parsed as Record<string, unknown>).filter(([, memo]) => {
    const candidate = memo as Partial<StudentMemo>;
    // reflection is absent in memos written before it existed, which are still good.
    const reflection = candidate.reflection;
    return !!memo && typeof candidate.themes === "string" && typeof candidate.surprise === "string"
      && Array.isArray(candidate.options) && candidate.options.every((option) => typeof option === "string")
      && (reflection === undefined
        || (Array.isArray(reflection) && reflection.every((answer) => typeof answer === "string")));
  })) as Record<string, StudentMemo>;
}

export default function InterviewPage() {
  return (
    <ThemeProvider>
      <StudyProvider>
        <WorkflowNav />
        <DemoScreens>{demo => <InterviewPageContent demoPlayback={demo} />}</DemoScreens>
      </StudyProvider>
    </ThemeProvider>
  );
}

function InterviewPageContent({ demoPlayback = false }: { demoPlayback?: boolean } = {}) {
  const [demoEnabled] = useDemoMode();
  const [demoRetry, setDemoRetry] = useState(0);
  const { studyId, studyBootstrapError } = useStudy();
  useEffect(() => {
    if (!demoPlayback || !studyId) return;
    let active = true;
    setError("");
    interviewOperation<{ batch: Batch }>(studyId, "demo/batch", {})
      .then(result => {
        if (!active) return;
        setBatch(result.batch);
        setStep(1);
      })
      .catch((failure: Error) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [studyId, demoPlayback, demoRetry]);

  const [personas, setPersonas] = useState<InterviewPersona[]>([]);
  // Empty means "the first N by the slider", which is every batch run so far.
  const [recruited, setRecruited] = useState<string[]>([]);
  // PA3.5 grades the student's own memo. Ours is the thing they check it against,
  // so theirs is what the export leads with and the only one they write.
  // One memo per batch, because a memo is an analysis OF a transcript: carried onto
  // another batch it would claim to be an analysis of interviews it never saw.
  // Restored in the mount effect, never during a render — reading localStorage while
  // rendering makes the prerendered HTML disagree with the client, and React does not
  // re-sync an input's value after hydration, so the student would watch their
  // writing vanish from fields that state still holds.
  const [memos, setMemos] = useState<Record<string, StudentMemo>>({});
  // A blocked or full store (Safari private browsing throws on setItem) must say so
  // while the text is still on screen, not after the reload that loses it.
  const [memoUnsaved, setMemoUnsaved] = useState("");
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
  const batchRequest = useRef<{ request_id: string; persona_count: number; interviewer_model: string; interviewee_model: string; allow_expensive_models: boolean; persona_ids?: string[] } | null>(null);
  const [step, setStep] = useState(0);
  const [themes, setThemes] = useState<Themes | null>(null);
  const [themesLoading, setThemesLoading] = useState(false);
  const readOnly = demoPlayback || !!batch?.demo;
  useEffect(() => {
    if (demoEnabled && !demoPlayback) { pauseBatch.current = true; setPausing(true); }
  }, [demoEnabled, demoPlayback]);
  const themeRequest = useRef(0);
  const stepTitle = useRef<HTMLHeadingElement | null>(null);
  function changeStep(next: number) { setStep(next); }
  useEffect(() => { stepTitle.current?.focus(); }, [step]);
  const busy = loading || comparisonLoading || batchLoading || regenerating || themesLoading;
  useDemoActivity(busy, demoPlayback);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (demoPlayback) return;
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
  const roomSize = recruited.length || personaCount;
  const memoKey = batch?.job_id ?? "";
  const myMemo = memos[memoKey] ?? EMPTY_MEMO;
  // Updater form, never a snapshot: two fields edited in one batch would otherwise
  // write the second one on top of a memo that had already lost the first.
  const editMemo = (update: (prev: StudentMemo) => StudentMemo) => {
    if (!memoKey) return;
    setMemos((prev) => {
      const next = { ...prev, [memoKey]: update(prev[memoKey] ?? EMPTY_MEMO) };
      try {
        if (!readOnly) localStorage.setItem(MEMO_STORE, JSON.stringify(next));
        setMemoUnsaved("");
      } catch {
        setMemoUnsaved("This browser is not saving your memo — copy it somewhere before you reload.");
      }
      return next;
    });
  };
  const interviewerModelEntry = models.find((entry) => entry.id === interviewerModel);
  const intervieweeModelEntry = models.find((entry) => entry.id === intervieweeModel);
  const preflightCostEstimate =
    interviewerModelEntry && intervieweeModelEntry
      ? estimateInterviewRunCost(roomSize, interviewerModelEntry, intervieweeModelEntry)
      : null;
  const modelsLocked = readOnly || turns.length > 0 || busy;

  function selectPersona(id: string) {
    if (activity.current) return;
    // The transcript and the comparison answers are what the student hands in, and both are
    // paid for. Selecting a persona discards them with no undo — including re-selecting the
    // current one, which is how you start over — so it asks first.
    const discards = [
      turns.length > 0
        ? `${turns.length} interview message${turns.length === 1 ? "" : "s"}`
        : "",
      comparisonResults.length > 0
        ? `${comparisonResults.length} compared model answer${comparisonResults.length === 1 ? "" : "s"}`
        : "",
    ].filter(Boolean);
    // Only the transcript has an export, so only offer that when there is one.
    const advice = turns.length > 0 ? " Export the transcript first if you need it." : "";
    if (
      discards.length > 0 &&
      !window.confirm(
        `${id === selectedId ? `Start over with ${id}?` : `Switch to ${id}?`} This discards ${discards.join(" and ")}${id === selectedId ? "" : ` from ${selectedId}`}, and they cannot be recovered.${advice}`
      )
    ) {
      return;
    }
    generation.current += 1;
    setSelectedId(id);
    setTurns([]);
    setSessionId(null);
    setSystemPrompt("");
    setError("");
    setExpensiveOptIn(false);
    setInterviewerModel((current) =>
      resetExpensiveModelSelection(models, current, defaultModelId)
    );
    setIntervieweeModel((current) =>
      resetExpensiveModelSelection(models, current, defaultModelId)
    );
    setComparisonExpensiveOptIn(false);
    setComparisonModelIds((current) => {
      const affordable = removeExpensiveComparisonModels(models, current);
      return canRunInterviewComparison(affordable)
        ? affordable
        : defaultInterviewComparisonModelIds(models);
    });
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
    if (readOnly || isDemoMode()) return;
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
    if (readOnly || isDemoMode()) return;
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
    if (!demoPlayback) {
      try { setMemos(readMemos(localStorage.getItem(MEMO_STORE))); } catch { /* ignore */ }
    }
    if (demoPlayback) return;
    const saved = localStorage.getItem(`interview-batch:${studyId}`);
    const savedRequest = localStorage.getItem(`interview-batch-request:${studyId}`);
    if (savedRequest) {
      try { batchRequest.current = JSON.parse(savedRequest); } catch { /* Ignore invalid local recovery data. */ }
    }
    let active = true;
    interviewOperation<{ batches: Batch[] }>(studyId, "batches")
      .then(({ batches }) => {
        if (active) setBatchHistory(previous => [
          // Demo playback lives only on the demo screen; listing it here would lock live controls.
          ...previous, ...batches.filter(item => !item.demo && !previous.some(saved => saved.job_id === item.job_id)),
        ]);
      })
      .catch((err: Error) => { if (active) setError(err.message); });
    if (saved) interviewOperation<{ batch: Batch }>(studyId, `batches/${encodeURIComponent(saved)}`)
      .then(({ batch: recovered }) => { if (active && !recovered.demo) setBatch(previous => previous ?? recovered); })
      .catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; pauseBatch.current = true; generation.current += 1; };
  }, [studyId]);

  async function runBatch(resume = false, recoverRequest = false) {
    if (readOnly || isDemoMode()) return;
    if (!studyId || activity.current || !interviewerModel || !intervieweeModel) return;
    const settings = resume && batch ? batch : recoverRequest ? batchRequest.current : {
      persona_count: roomSize, interviewer_model: interviewerModel, interviewee_model: intervieweeModel,
      allow_expensive_models: expensiveOptIn,
    };
    if (!settings) return;
    const interviewer = models.find(model => model.id === settings.interviewer_model);
    const interviewee = models.find(model => model.id === settings.interviewee_model);
    if (!interviewer || !interviewee) return;
    const estimate = estimateInterviewRunCost(settings.persona_count, interviewer, interviewee);
    // Name the room in the dialog: a recovered request can carry one that no longer
    // matches the checkboxes on screen, and that is what the student is authorizing.
    const room = ("persona_ids" in settings && settings.persona_ids?.length
      ? settings.persona_ids.join(", ") : recruited.length && !resume && !recoverRequest
        ? recruited.join(", ") : `first ${settings.persona_count}`);
    if (!window.confirm(`${resume ? "Resume" : recoverRequest ? "Recover" : "Start"} batch: ${settings.persona_count} personas (${room})\nInterviewer: ${settings.interviewer_model}\nInterviewee: ${settings.interviewee_model}\nEstimated full-run cost: ${formatInterviewRunCostEstimate(estimate)} (actual cost may differ).${resume && batch?.status === "failed" ? "\nThe previous provider outcome may be unknown. Retrying may add another charge." : ""}\nAuthorize this run?`)) return;
    themeRequest.current += 1;
    setThemes(null);
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
        const request = (recoverRequest ? batchRequest.current : null) ?? {
          request_id: crypto.randomUUID(), persona_count: roomSize,
          interviewer_model: interviewerModel, interviewee_model: intervieweeModel,
          allow_expensive_models: expensiveOptIn,
          // Only a hand-picked room sends ids; the server keeps its first-N default.
          ...(recruited.length ? { persona_ids: recruited } : {}),
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
        if (isDemoMode() || pauseBatch.current || current.status === "completed" || current.status === "budget_stopped") break;
        current = (await interviewOperation<{ batch: Batch }>(studyId, `batches/${current.job_id}/advance`, { revision: current.revision, retry: resume && current.status === "failed" })).batch;
        setBatch(current);
        const updated = current;
        setBatchHistory(previous => previous.map(item => item.job_id === updated.job_id ? updated : item));
      } while (current.status === "running");
    } catch (err) {
      setError(`${(err as Error).message} Use Recover earlier request to re-submit its displayed settings, or Resume batch for saved progress.`);
    } finally {
      setBatchLoading(false);
      activity.current = false;
    }
  }

  async function loadThemes(generate = false) {
    if (generate && (readOnly || isDemoMode())) return;
    if (!studyId || !batch || activity.current) return;
    const runId = batch.job_id;
    const token = ++themeRequest.current;
    if (generate && (!themes || themes.from_run_id !== runId || !window.confirm(
      `${themes.saved?.message ?? "Extract themes from this completed batch."}\nModel: ${themes.model}\nEstimated additional cost: $${Number(themes.estimated_cost_usd).toFixed(4)} (actual cost may differ).\nAuthorize this extraction charge?`))) return;
    activity.current = true;
    setThemesLoading(true);
    setError("");
    try {
      const response = await interviewOperation<{ insights: Themes }>(studyId, `batches/${runId}/themes`, generate ? {
        revision: themes!.revision, authorize_charge: true,
        ...(themes!.saved && !themes!.stale ? { retry_attempt: themes!.saved.attempt } : {}),
      } : undefined);
      if (token === themeRequest.current && response.insights.from_run_id === runId) {
        setThemes(response.insights);
        if (response.insights.session_usage) {
          const updated = { ...batch, session_usage: response.insights.session_usage };
          setBatch(updated);
          setBatchHistory(previous => previous.map(item => item.job_id === runId ? updated : item));
        }
      }
    } catch (err) {
      if (token === themeRequest.current) {
        setThemes(null);
        setError(`${(err as Error).message} Transcripts are preserved. If a generation request timed out, its billing outcome may be unknown. Check saved themes before explicitly retrying.`);
      }
    } finally { setThemesLoading(false); activity.current = false; }
  }

  async function regenerate(answerId: string, version: number, comparison: boolean) {
    if (readOnly || isDemoMode()) return;
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
      {readOnly ? <DemoNotice provisional={batch?.provisional} /> : null}
      {demoPlayback && !batch && !error ? <p role="status">Loading demo…</p> : null}
      {demoPlayback && error ? <Button onClick={() => setDemoRetry(n => n + 1)}>Retry demo load</Button> : null}

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
          hidden={step !== 0}
          href="/prerecorded-interviews.html"
          className="mt-5 inline-flex items-center gap-2 rounded-xl border border-app-border px-4 py-2.5 text-sm font-semibold text-app-text transition hover:border-[var(--color-gold)] hover:text-[var(--color-gold)]"
        >
          Browse pre-recorded interviews
          <span aria-hidden="true">&rarr;</span>
        </a>
        <p hidden={step !== 0} className="mt-2 max-w-2xl text-xs leading-5 text-app-muted">
          Complete eight-turn interviews for all 30 personas on both of Dr. Lin&rsquo;s recommended
          models, recorded ahead of time. Replaying one costs nothing.
        </p>

        <a
          href="/interview/you"
          className="mt-5 inline-flex items-center gap-2 rounded-xl border border-app-border px-4 py-2.5 text-sm font-semibold text-app-text transition hover:border-[var(--color-gold)] hover:text-[var(--color-gold)]"
        >
          AI interviews you
          <span aria-hidden="true">&rarr;</span>
        </a>
        <p className="mt-2 max-w-2xl text-xs leading-5 text-app-muted">
          Flip the roles: the AI moderator asks you the discussion guide&rsquo;s questions and follows up on your answers.
        </p>

        <nav aria-label="Interview steps" className="my-5 flex flex-wrap gap-3">
          {["1. Choose", "2. Interview", "3. Themes"].map((label, index) =>
            <Button key={label} variant="secondary" aria-current={step === index ? "step" : undefined} onClick={() => changeStep(index)}>{label}</Button>)}
        </nav>
        <h2 ref={stepTitle} tabIndex={-1} className="text-xl font-semibold">{["Choose personas and models", "Run interviews or try a question", "Compare with your hand-coding"][step]}</h2>
        <p>{["Choose your models and batch size, then continue to interview.", "Run the batch, or explore the optional comparison and follow-up tools.", "Read and hand-code your batch transcripts first. Then explicitly generate themes to compare."][step]}</p>
        <div className="my-3 flex gap-3">
          {step > 0 ? <Button variant="secondary" onClick={() => changeStep(step - 1)}>Back</Button> : null}
          {step < 2 ? <Button onClick={() => changeStep(step + 1)}>Continue</Button> : null}
        </div>
        {error ? <p role="alert">{error}</p> : null}
        {step === 2 ? <GlassPanel className="p-5">
          <p>Themes are available for completed batches. Single-question explorations remain in the Interview step.</p>
          <Button disabled={!batch || busy} onClick={() => loadThemes()}>Check saved themes (free)</Button>
          {themesLoading ? <p role="status">Loading themes…</p> : null}
          <section className="my-5 border-t border-app-border pt-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">Your memo</p>
            <p className="mt-2 text-xs leading-5 text-app-muted">
              This is the one you hand in. Write it from the transcripts; what the model
              found is below, to check yourself against, and it is labelled that way in
              the download.
            </p>
            {memoKey ? null : <p role="alert" className="mt-2 text-xs text-app-muted">
              Select a batch first — a memo is saved against the interviews it is about.
            </p>}
            {memoUnsaved ? <p role="alert" className="mt-2 text-xs">{memoUnsaved}</p> : null}
            <label className="mt-3 block text-sm">Themes you heard
              <textarea aria-label="Your themes" disabled={!memoKey} rows={4} value={myMemo.themes}
                onChange={(event) => editMemo((prev) => ({ ...prev, themes: event.target.value }))}
                className="mt-1 w-full rounded-xl border border-app-border bg-transparent p-2 text-sm" />
            </label>
            <label className="mt-3 block text-sm">One surprise
              <textarea aria-label="Your surprise" disabled={!memoKey} rows={2} value={myMemo.surprise}
                onChange={(event) => editMemo((prev) => ({ ...prev, surprise: event.target.value }))}
                className="mt-1 w-full rounded-xl border border-app-border bg-transparent p-2 text-sm" />
            </label>
            <p className="mt-3 text-sm">Closed-ended answer options, in participants&rsquo; words</p>
            {myMemo.options.map((option, index) => <input key={index} aria-label={`Your answer option ${index + 1}`} disabled={!memoKey}
              value={option} onChange={(event) => editMemo((prev) => ({ ...prev,
                options: prev.options.map((existing, at) => at === index ? event.target.value : existing) }))}
              className="mt-2 w-full rounded-xl border border-app-border bg-transparent p-2 text-sm" />)}
            <button type="button" className="mt-2 text-xs underline"
              onClick={() => editMemo((prev) => ({ ...prev, options: [...prev.options, ""] }))}>
              Add another option
            </button>
          </section>
          <section className="my-5 border-t border-app-border pt-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">AI reflection</p>
            <p className="mt-2 text-xs leading-5 text-app-muted">
              Required by PA3.5, and answered after you have read what the model found.
              Two to four sentences each, specific to this session rather than to AI in general.
            </p>
            {REFLECTION_PROMPTS.map((prompt, index) => (
              <label key={index} className="mt-3 block text-sm">{prompt}
                {/* The prompt itself is the accessible name: an ordinal would leave the
                    four fields indistinguishable to a screen reader. */}
                <textarea aria-label={prompt} disabled={!memoKey} rows={2}
                  value={myMemo.reflection?.[index] ?? ""}
                  onChange={(event) => editMemo((prev) => ({ ...prev, reflection:
                    REFLECTION_PROMPTS.map((_, at) => at === index
                      ? event.target.value : prev.reflection?.[at] ?? "") }))}
                  className="mt-1 w-full rounded-xl border border-app-border bg-transparent p-2 text-sm" />
              </label>
            ))}
          </section>
          {themes && themes.from_run_id === batch?.job_id ? <div aria-live="polite">
            <p>{themes.message}</p>
            {themes.stale ? <p>These themes belong to an earlier transcript version. Generate again to compare the current version.</p> : null}
            {themes.saved?.message ? <p role="alert">{themes.saved.message}</p> : null}
            {themes.saved?.budget_stop ? <p role="alert">{themes.saved.budget_stop}</p> : null}
            {!readOnly && themes.eligible && (!themes.available || themes.stale) ? <Button disabled={readOnly || busy} onClick={() => loadThemes(true)}>
              {themes.saved && !themes.stale ? "Retry extraction" : "Generate themes"} (about ${Number(themes.estimated_cost_usd).toFixed(4)} extra)
            </Button> : null}
            {themes.emotion && themes.emotion.interviewed > 0 ? <section className="my-4">
              <h3 className="font-semibold">Emotion across the room ({themes.emotion.scored === themes.emotion.interviewed
                ? `${themes.emotion.scored} interviewed`
                : `${themes.emotion.scored} of ${themes.emotion.interviewed} interviewed scored`}, {themes.emotion.answers} answers)</h3>
              <p className="text-sm text-app-muted">{themes.emotion.label} · no charge · counted per answer, not per interviewee</p>
              <p>{["positive", "neutral", "negative"].map((name) =>
                `${themes.emotion!.counts[name] ?? 0} ${name}`).join(" · ")}</p>
              <ul className="mt-2 text-sm">
                {themes.emotion.personas.map((entry, index) => <li key={`${entry.persona_id ?? "?"}-${index}`}>
                  {entry.persona_id ?? "unidentified"}: {entry.positive} positive · {entry.neutral} neutral · {entry.negative} negative
                  {" "}of {entry.classified === entry.answers
                    ? `${entry.answers} answers`
                    : `${entry.classified} of ${entry.answers} answers read`} · fit {entry.fit_tier}
                </li>)}
              </ul>
              <p className="mt-2 text-sm text-app-muted">
                Keyword-based, and far better at catching voiced concern than voiced enthusiasm.
                Use the per-theme sentiment above for the considered read.
              </p>
            </section> : null}
            {themes.saved?.themes?.length ? <p className="mt-4 text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">What the model found — for comparison, not for submission</p> : null}
            {themes.saved?.themes?.map((theme, index) => <article className="my-4" key={index}>
              <h3 className="font-semibold">{theme.label} · {theme.sentiment}</h3><p>{theme.synthesis}</p>
              <blockquote>“{theme.representative_quote}”</blockquote>
              <a className="underline" href={`#${demoPlayback ? "demo-" : ""}transcript-${theme.quote_persona_id}`} onClick={() => {
                const transcript = document.getElementById(`${demoPlayback ? "demo-" : ""}transcript-${theme.quote_persona_id}`);
                transcript?.setAttribute("open", "");
              }}>{theme.quote_persona_id} — locate interviewee quote</a>
            </article>)}
            {themes.saved?.themes?.length && themes.saved.surprise ? <article className="my-4">
              <h3 className="font-semibold">One surprise</h3>
              <p>{themes.saved.surprise.summary}</p>
              <blockquote>“{themes.saved.surprise.quote}”</blockquote>
              <a className="underline" href={`#${demoPlayback ? "demo-" : ""}transcript-${themes.saved.surprise.quote_persona_id}`} onClick={() => {
                document.getElementById(`${demoPlayback ? "demo-" : ""}transcript-${themes.saved!.surprise!.quote_persona_id}`)?.setAttribute("open", "");
              }}>{themes.saved.surprise.quote_persona_id} — locate interviewee quote</a>
            </article> : null}
            {themes.saved?.themes?.length && themes.saved.answer_options?.length ? <article className="my-4">
              <h3 className="font-semibold">Closed-ended answer options</h3>
              <p className="text-sm text-app-muted">Each one is a participant&rsquo;s own wording, copied from an answer.</p>
              <ul className="mt-2 list-disc pl-5">
                {themes.saved.answer_options.map((option, index) => <li key={index}>
                  “{option.text}” — <a className="underline" href={`#${demoPlayback ? "demo-" : ""}transcript-${option.quote_persona_id}`} onClick={() => {
                    document.getElementById(`${demoPlayback ? "demo-" : ""}transcript-${option.quote_persona_id}`)?.setAttribute("open", "");
                  }}>{option.quote_persona_id}</a>
                </li>)}
              </ul>
            </article> : null}
          </div> : null}
        </GlassPanel> : null}
        {regenerationCost ? <p className="mt-3 text-sm" role="status">Measured session cost after regeneration: ${Number(regenerationCost).toFixed(6)}</p> : null}
        {regenerating ? <p role="status">Regenerating answer…</p> : null}
        <div className={cn("mt-8 grid gap-5", step === 0 && "lg:grid-cols-[22rem_minmax(0,1fr)]")}>
          <GlassPanel hidden={step !== 0} style={{ display: step !== 0 ? "none" : undefined }} className="p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
              Personas ({personas.length})
            </p>
            <div className="fine-scrollbar mt-4 flex max-h-[26rem] flex-col gap-2 overflow-y-auto pr-1">
              {personas.map((entry) => (
                <button
                  key={entry.persona_id}
                  type="button"
                  onClick={() => selectPersona(entry.persona_id)}
                  disabled={readOnly || busy || exportingFormat !== null}
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
            <GlassPanel hidden={step !== 0} style={{ display: step !== 0 ? "none" : undefined }} className="p-5">
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
                    {roomSize} personas
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

                <div className="mt-5 border-t border-app-border pt-5">
                  <div className="flex items-center justify-between gap-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">
                      Recruit the room
                    </p>
                    {recruited.length ? <button type="button" className="text-xs underline"
                      onClick={() => setRecruited([])} disabled={modelsLocked}>
                      Clear ({recruited.length})
                    </button> : null}
                  </div>
                  <p className="mt-2 text-xs leading-5 text-app-muted">
                    {recruited.length
                      ? `Interviewing the ${recruited.length} you picked: ${recruited.join(", ")}.`
                      : `No one picked, so the run takes the first ${personaCount} on the roster. Tick anyone to recruit them instead.`}
                  </p>
                  <div aria-label="Recruit the room" className="fine-scrollbar mt-3 flex max-h-[14rem] flex-col gap-1 overflow-y-auto pr-1">
                    {personas.map((entry) => (
                      <label key={entry.persona_id} className="flex items-start gap-2 text-xs leading-5">
                        <input
                          type="checkbox"
                          aria-label={`Recruit ${entry.persona_id}`}
                          checked={recruited.includes(entry.persona_id)}
                          disabled={modelsLocked}
                          onChange={() => setRecruited(recruited.includes(entry.persona_id)
                            ? recruited.filter((id) => id !== entry.persona_id)
                            // Appended, so the room runs in the order it was recruited.
                            : [...recruited, entry.persona_id])}
                          className="mt-1 size-4 accent-[var(--color-gold)] disabled:cursor-not-allowed"
                        />
                        <span>
                          <span className="font-semibold text-app-text">{entry.persona_id}</span>
                          <span className="block text-app-muted">
                            {entry.census_profile.split(".").slice(0, 2).join(".") || "\u2014"}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                  {recruited.length && recruited.length < personaCountRange.minimum ? (
                    <p role="alert" className="mt-2 text-xs text-app-muted">
                      A room needs at least {personaCountRange.minimum} people. Pick {personaCountRange.minimum - recruited.length} more.
                    </p>
                  ) : null}
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
                    For {roomSize} personas with both selected models
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

            <GlassPanel hidden={step === 0} style={{ display: step === 0 ? "none" : undefined }} className="p-5" aria-label="AI-to-AI batch results">
              <div className="flex flex-wrap gap-2">
                <Button disabled={readOnly || busy || !studyId || !interviewerModel || !intervieweeModel || (recruited.length > 0 && recruited.length < personaCountRange.minimum)} onClick={() => runBatch()}>
                  Run AI-to-AI batch ({roomSize} personas)
                </Button>
                {batchRequest.current ? (
                  <Button variant="secondary" disabled={readOnly || busy} onClick={() => runBatch(false, true)}>
                    Recover earlier request: {batchRequest.current.persona_count} personas ({batchRequest.current.persona_ids?.length ? batchRequest.current.persona_ids.join(", ") : `first ${batchRequest.current.persona_count}`}) · interviewer {batchRequest.current.interviewer_model} · interviewee {batchRequest.current.interviewee_model} · expensive models {batchRequest.current.allow_expensive_models ? "enabled" : "disabled"} (re-submit and run)
                  </Button>
                ) : null}
                {batch && (batch.status === "running" || batch.status === "failed") ? (
                  <Button variant="secondary" disabled={readOnly || busy} onClick={() => runBatch(true)}>Resume batch</Button>
                ) : null}
                {batchLoading ? <Button variant="secondary" disabled={pausing} onClick={() => { pauseBatch.current = true; setPausing(true); }}>Pause after this call</Button> : null}
              </div>
              <p className="mt-2 text-xs text-app-muted">Eight adaptive questions per persona using the fixed household set and Tahoe Mini research brief. Cached interviews replay free.</p>
              {batchHistory.length > 0 ? <label className="mt-4 block">Saved batches
                <select aria-label="Saved batches" disabled={readOnly || busy} value={batch?.job_id ?? ""}
                  onChange={event => {
                    const selected = batchHistory.find(item => item.job_id === event.target.value);
                    if (selected && studyId) {
                      themeRequest.current += 1; setThemes(null);
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
                  const exported = batchExport(batch, format, themes?.stale ? undefined : themes?.saved, memos[batch.job_id]);
                  const url = URL.createObjectURL(exported.blob);
                  const link = document.createElement("a");
                  link.href = url; link.download = exported.filename;
                  document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
                }}>{format === "csv" ? "Download batch CSV" : "Export transcript + memo"}</Button>)}</div>
                {batch.error ? <p role="alert">{batch.error.details?.scope ? `${batch.error.details.scope} cap: ` : ""}{batch.error.message}</p> : null}
                {batch.transcripts.map(transcript => <details id={`${demoPlayback ? "demo-" : ""}transcript-${transcript.persona_id}`} key={transcript.persona_id} className="rounded-xl border border-app-border p-3">
                  <summary>{transcript.persona_id} · {Math.floor(transcript.messages.length / 2)}/{batch.turn_limit} answers</summary>
                  {transcript.messages.map((message, index) => <p key={index} className="mt-3 whitespace-pre-wrap text-sm leading-6"><strong>{message.role === "user" ? "Interviewer" : transcript.persona_id}: </strong>{message.content}</p>)}
                </details>)}
              </div> : batchLoading ? <p role="status">Starting batch…</p> : null}
            </GlassPanel>

            <GlassPanel hidden={step !== 1} style={{ display: step !== 1 ? "none" : undefined }} className="p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-app-muted">
                Interviewing ({selectedId || "nobody yet"})
              </p>
            <div className="fine-scrollbar mt-4 flex max-h-[26rem] flex-col gap-2 overflow-y-auto pr-1">
              {personas.map((entry) => (
                <button
                  key={entry.persona_id}
                  type="button"
                  onClick={() => selectPersona(entry.persona_id)}
                  disabled={readOnly || busy || exportingFormat !== null}
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
              <p className="mt-2 text-xs leading-5 text-app-muted">
                Choosing someone starts a fresh conversation with that household.
              </p>
            </GlassPanel>

            {persona ? (
              <GlassPanel hidden={step !== 1} style={{ display: step !== 1 ? "none" : undefined }} className="p-5">
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

            <details hidden={step !== 1}><summary>Optional: compare model answers</summary>
            <GlassPanel hidden={step !== 1} style={{ display: step !== 1 ? "none" : undefined }} className="p-5">
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

              <fieldset className="mt-5" disabled={readOnly || busy}>
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
                  disabled={readOnly || busy}
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
                  disabled={readOnly || busy}
                  placeholder="Ask every model the same question…"
                  className="flex-1 rounded-xl border border-app-border bg-transparent px-4 py-3 text-sm text-app-text outline-none transition placeholder:text-app-muted focus:border-app-borderStrong disabled:cursor-not-allowed disabled:opacity-60"
                />
                <Button
                  onClick={compareModels}
                  disabled={
                    readOnly || busy ||
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

                  {comparisonResults.find((result) => result.budgetStop) ? (
                    <p
                      role="alert"
                      className="mt-4 rounded-xl border border-app-border px-4 py-3 text-sm leading-6 text-app-text"
                    >
                      {comparisonResults.find((result) => result.budgetStop)?.budgetStop}
                    </p>
                  ) : null}

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
                          {result.answerId && result.answer ? <Button variant="secondary" disabled={readOnly || busy} onClick={() => regenerate(result.answerId!, result.version ?? 0, true)}>Regenerate answer (paid)</Button> : null}
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

            </details>

            <GlassPanel hidden={step !== 1} style={{ display: step !== 1 ? "none" : undefined }} className="flex min-h-[22rem] flex-col p-5">
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
                      {turn.answerId && index === turns.length - 1 ? <Button variant="secondary" disabled={readOnly || busy} onClick={() => regenerate(turn.answerId!, turn.version ?? 0, false)}>Regenerate answer (paid)</Button> : null}
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
                    readOnly || busy ||
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
              <GlassPanel hidden={step !== 1} style={{ display: step !== 1 ? "none" : undefined }} className="p-5">
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
