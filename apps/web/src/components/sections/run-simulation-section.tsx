"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  clearLatestSimulationRun,
  getLatestSimulationRun,
  getLatestStabilityCheck,
  SimulationJobPayload,
  SimulationRunConditions,
  SimulationRunResultPayload,
  SimulationStabilityResultPayload,
  startSimulationRun,
  startStabilityCheck,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";

type StatusTone = "neutral" | "success" | "warning" | "error";

type StatusState = {
  tone: StatusTone;
  message: string;
};

const EXECUTION_PHASES = [
  "Validating setup",
  "Resolving geography",
  "Generating personas",
  "Generating responses",
  "Saving results",
  "Completed",
] as const;

const PERSONAS_PER_PAGE = 6;
const RESPONSE_RECORDS_PER_PAGE = 5;

const EMPTY_STATUS: StatusState = {
  tone: "neutral",
  message:
    "Review the saved setup, confirm the trust conditions, and launch the study when you are ready.",
};

export function RunSimulationSection() {
  const {
    studyId,
    study,
    createOrLoadStudy,
    isCreatingStudy,
    isHydratingStudy,
    refreshStudy,
  } = useStudy();
  const { scrollToSection, setNavigationLocked } = useSectionRegistry();
  const [latestRun, setLatestRun] =
    useState<SimulationJobPayload<SimulationRunResultPayload> | null>(null);
  const [latestStabilityCheck, setLatestStabilityCheck] =
    useState<SimulationJobPayload<SimulationStabilityResultPayload> | null>(null);
  const [status, setStatus] = useState<StatusState>(EMPTY_STATUS);
  const [stabilityStatus, setStabilityStatus] = useState<StatusState>({
    tone: "neutral",
    message: "Run the main study first, then use Stability Check as a lightweight repeatability pass.",
  });
  const [isRunning, setIsRunning] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [isRunningStability, setIsRunningStability] = useState(false);
  const [executionPhaseIndex, setExecutionPhaseIndex] = useState(0);
  const [repeatRuns, setRepeatRuns] = useState(3);
  const [personaPage, setPersonaPage] = useState(0);
  const [responseRecordPage, setResponseRecordPage] = useState(0);
  const progressTimerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function hydrateRunState() {
      if (!studyId || !study) {
        if (!cancelled) {
          setLatestRun(null);
          setLatestStabilityCheck(null);
          setStatus(EMPTY_STATUS);
          setStabilityStatus({
            tone: "neutral",
            message:
              "Run the main study first, then use Stability Check as a lightweight repeatability pass.",
          });
        }
        return;
      }

      try {
        const [runResult, stabilityResult] = await Promise.all([
          getLatestSimulationRun(studyId),
          getLatestStabilityCheck(studyId),
        ]);

        if (cancelled) {
          return;
        }

        setLatestRun(runResult);
        setLatestStabilityCheck(stabilityResult);
        setStatus(buildRunStatus(runResult, study));
        setStabilityStatus(buildStabilityStatus(stabilityResult));
      } catch (error) {
        if (!cancelled) {
          setStatus({
            tone: "warning",
            message:
              error instanceof Error
                ? error.message
                : "Unable to load the latest run state right now.",
          });
        }
      }
    }

    void hydrateRunState();

    return () => {
      cancelled = true;
    };
  }, [
    studyId,
    study?.updated_at,
    study?.audience?.updated_at,
    study?.product?.updated_at,
    study?.market?.updated_at,
    study?.survey?.updated_at,
    study?.experiment?.updated_at,
    study?.derived?.latest_persona_preview?.completed_at,
  ]);

  useEffect(() => {
    setNavigationLocked(isRunning);

    return () => {
      setNavigationLocked(false);
    };
  }, [isRunning, setNavigationLocked]);

  useEffect(() => {
    return () => {
      if (progressTimerRef.current !== null) {
        window.clearInterval(progressTimerRef.current);
      }
    };
  }, []);

  const runReady = useMemo(() => isReadyToRun(study), [study]);
  const readinessBanner = useMemo(() => buildReadinessBanner(study), [study]);
  const trustConditions = useMemo(
    () => latestRun?.result?.run_conditions ?? buildPredictedRunConditions(study),
    [latestRun?.result?.run_conditions, study]
  );
  const runDebugSummary = latestRun?.result?.run_debug_summary ?? null;
  const latestRunWarnings = latestRun?.result?.warnings ?? [];
  const latestParseWarnings = latestRun?.result?.survey_parse_warnings ?? [];
  const allPersonas = latestRun?.result?.personas ?? [];
  const allResponseRecords =
    latestRun?.result?.response_records?.length
      ? latestRun.result.response_records
      : latestRun?.result?.response_record_preview ?? [];
  const personaPageCount =
    allPersonas.length > 0 ? Math.ceil(allPersonas.length / PERSONAS_PER_PAGE) : 0;
  const responseRecordPageCount =
    allResponseRecords.length > 0
      ? Math.ceil(allResponseRecords.length / RESPONSE_RECORDS_PER_PAGE)
      : 0;
  const personaPreviewRows = useMemo(
    () => paginateItems(allPersonas, personaPage, PERSONAS_PER_PAGE),
    [allPersonas, personaPage]
  );
  const recordPreviewRows = useMemo(
    () => paginateItems(allResponseRecords, responseRecordPage, RESPONSE_RECORDS_PER_PAGE),
    [allResponseRecords, responseRecordPage]
  );
  const stabilityRows = latestStabilityCheck?.result?.stability_table ?? [];

  useEffect(() => {
    setPersonaPage(0);
    setResponseRecordPage(0);
  }, [latestRun?.job_id]);

  useEffect(() => {
    setPersonaPage((current) => Math.min(current, Math.max(personaPageCount - 1, 0)));
  }, [personaPageCount]);

  useEffect(() => {
    setResponseRecordPage((current) =>
      Math.min(current, Math.max(responseRecordPageCount - 1, 0))
    );
  }, [responseRecordPageCount]);

  function startProgressAnimation() {
    setExecutionPhaseIndex(0);
    if (progressTimerRef.current !== null) {
      window.clearInterval(progressTimerRef.current);
    }
    progressTimerRef.current = window.setInterval(() => {
      setExecutionPhaseIndex((current) =>
        Math.min(current + 1, EXECUTION_PHASES.length - 2)
      );
    }, 820);
  }

  function stopProgressAnimation(finalIndex: number) {
    if (progressTimerRef.current !== null) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    setExecutionPhaseIndex(finalIndex);
  }

  async function handleRunStudy() {
    if (!runReady) {
      setStatus(readinessBanner);
      return;
    }

    setIsRunning(true);
    setStatus({
      tone: "neutral",
      message:
        "Run started. The backend currently returns the completed result in one response, while the UI maps progress phases locally for a stronger launch experience.",
    });
    startProgressAnimation();

    try {
      const resolvedStudyId = (await createOrLoadStudy()) ?? studyId;
      if (!resolvedStudyId) {
        throw new Error("No study is available yet.");
      }

      const result = await startSimulationRun(resolvedStudyId);
      await refreshStudy(resolvedStudyId);
      setLatestRun(result.simulationRun);
      stopProgressAnimation(EXECUTION_PHASES.length - 1);
      setStatus(buildRunStatus(result.simulationRun, study));
    } catch (error) {
      stopProgressAnimation(Math.max(executionPhaseIndex, 1));
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to run the study right now.",
      });
    } finally {
      setIsRunning(false);
    }
  }

  async function handleClearRun() {
    if (!studyId) {
      return;
    }

    setIsClearing(true);
    try {
      await clearLatestSimulationRun(studyId);
      setLatestRun(null);
      setLatestStabilityCheck(null);
      setStatus({
        tone: "success",
        message: "Saved simulation result and stability outputs were cleared.",
      });
      setStabilityStatus({
        tone: "neutral",
        message:
          "Run the main study first, then use Stability Check as a lightweight repeatability pass.",
      });
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to clear the saved simulation result right now.",
      });
    } finally {
      setIsClearing(false);
    }
  }

  async function handleRunStabilityCheck() {
    if (!studyId || !latestRun?.result) {
      setStabilityStatus({
        tone: "warning",
        message: "Complete the main study run first, then launch a stability check.",
      });
      return;
    }

    setIsRunningStability(true);
    setStabilityStatus({
      tone: "neutral",
      message: "Running lightweight repeatability checks...",
    });

    try {
      const result = await startStabilityCheck(studyId, repeatRuns);
      setLatestStabilityCheck(result);
      setStabilityStatus(buildStabilityStatus(result));
    } catch (error) {
      setStabilityStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to run the stability check right now.",
      });
    } finally {
      setIsRunningStability(false);
    }
  }

  return (
    <SectionWrapper id="run-simulation" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_23rem] xl:grid-cols-[minmax(0,1.02fr)_25rem] 2xl:grid-cols-[minmax(0,1.02fr)_29rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={7}
              eyebrow="Run Simulation"
              title="Launch the grounded study with a clear view of what is about to happen."
              description="This is the execution chapter: review the saved setup, confirm the trust conditions, and run the study through the configured models before moving into Analysis."
            />
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <StatusBanner tone={readinessBanner.tone} message={readinessBanner.message} />
          </RevealOnScroll>

          <GlassPanel className="p-5 sm:p-6">
            <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
              <div className="flex flex-wrap items-center gap-3">
                <BadgeChip tone="cyan">Trust Conditions</BadgeChip>
                <BadgeChip tone={runReady ? "cyan" : "gold"}>
                  {runReady ? "Runnable" : "Not ready yet"}
                </BadgeChip>
              </div>

              <p className="mt-4 max-w-3xl text-sm leading-6 text-app-muted">
                This panel explains what grounding and fallback conditions the run will actually use. It is part of the product’s trust story, not background metadata.
              </p>

              <div className="mt-5 grid gap-3 md:grid-cols-2">
                <TrustConditionCard
                  title="Context influence"
                  status={trustConditions.context_influence?.enabled ? "enabled" : "degraded"}
                  detail={
                    trustConditions.context_influence?.enabled
                      ? `Using ${summarizeList(
                          trustConditions.context_influence?.sources ?? [],
                          3
                        )} to frame responses.`
                      : "Context influence is unavailable."
                  }
                />
                <TrustConditionCard
                  title="Geography-aware priors"
                  status={trustConditions.geography_aware_priors?.status ?? "unknown"}
                  detail={
                    trustConditions.geography_aware_priors?.detail ??
                    "This will resolve once the run begins."
                  }
                />
                <TrustConditionCard
                  title="Grounded priors"
                  status={trustConditions.grounded_priors?.status ?? "unknown"}
                  detail={
                    trustConditions.grounded_priors?.detail ??
                    "This will resolve once the run begins."
                  }
                />
                <TrustConditionCard
                  title="Affordability priors"
                  status={trustConditions.affordability_priors?.status ?? "unknown"}
                  detail={
                    trustConditions.affordability_priors?.detail ??
                    "This will resolve once the run begins."
                  }
                />
                <TrustConditionCard
                  title="Generation mode"
                  status={trustConditions.generation_mode === "openrouter_live" ? "enabled" : "degraded"}
                  detail={
                    trustConditions.generation_mode === "openrouter_live"
                      ? "OpenRouter live path is active for this saved run."
                      : trustConditions.generation_mode === "mock"
                        ? "Mock fallback path is active."
                        : "The backend will resolve live-vs-fallback mode when the run starts."
                  }
                />
                <TrustConditionCard
                  title="Selected models"
                  status={(trustConditions.selected_models?.length ?? 0) > 0 ? "enabled" : "unknown"}
                  detail={
                    (trustConditions.selected_models?.length ?? 0) > 0
                      ? summarizeList(trustConditions.selected_models ?? [], 3)
                      : "No models are available yet."
                  }
                />
              </div>
            </div>
          </GlassPanel>

          <GlassPanel className="p-5 sm:p-6">
            <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
              <div className="flex flex-wrap items-center gap-3">
                <BadgeChip tone="gold">Launch Control</BadgeChip>
                <BadgeChip tone={isRunning ? "cyan" : "neutral"}>
                  {isRunning ? "Execution active" : "Ready to launch"}
                </BadgeChip>
              </div>

              <p className="mt-4 max-w-2xl text-sm leading-6 text-app-muted">
                Starting the run will validate the saved setup, resolve available grounding context, generate personas, generate responses, and save the result for later Analysis.
              </p>

              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <Button
                  onClick={handleRunStudy}
                  disabled={!runReady || isRunning || isCreatingStudy || isHydratingStudy}
                >
                  {isRunning ? "Running Study..." : "Run Study"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={handleClearRun}
                  disabled={isRunning || isClearing || (!latestRun && !latestStabilityCheck)}
                >
                  {isClearing ? "Clearing..." : "Clear Saved Simulation Result"}
                </Button>
              </div>

              <div className="mt-5">
                <StatusBanner tone={status.tone} message={status.message} compact />
              </div>

              {isRunning ? (
                <div className="mt-5 rounded-[1.35rem] border border-app-cyan/20 bg-[rgba(15,216,255,0.06)] p-4">
                  <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-cyan">
                    Execution progress
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {EXECUTION_PHASES.map((phase, index) => {
                      const state =
                        index < executionPhaseIndex
                          ? "complete"
                          : index === executionPhaseIndex
                            ? "active"
                            : "pending";
                      return (
                        <div
                          key={phase}
                          className={cn(
                            "rounded-[1.2rem] border px-4 py-3 text-sm transition",
                            state === "complete" &&
                              "border-app-cyan/25 bg-[rgba(15,216,255,0.12)] text-app-cyan",
                            state === "active" &&
                              "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
                            state === "pending" &&
                              "border-white/8 bg-white/[0.03] text-app-muted"
                          )}
                        >
                          {phase}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          </GlassPanel>

          {latestRun ? (
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <BadgeChip tone="cyan">Run Result</BadgeChip>
                  <BadgeChip tone={latestRun.status === "completed" ? "cyan" : "gold"}>
                    {latestRun.status === "completed" ? "Completed" : latestRun.status}
                  </BadgeChip>
                </div>

                {latestRun.result ? (
                  <>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <MetaCard label="Run ID" value={latestRun.result.run_id} />
                      <MetaCard
                        label="Requested responses"
                        value={String(latestRun.result.total_requested_responses)}
                      />
                      <MetaCard
                        label="Generated responses"
                        value={String(latestRun.result.total_generated_responses)}
                      />
                      <MetaCard
                        label="Experiment mode"
                        value={formatMode(latestRun.result.experiment_mode)}
                      />
                      <MetaCard
                        label="Models used"
                        value={summarizeList(latestRun.result.models_used ?? [], 2)}
                      />
                      <MetaCard
                        label="Generation mode"
                        value={formatGenerationMode(latestRun.result.generation_mode)}
                      />
                      <MetaCard
                        label="Survey title"
                        value={latestRun.result.survey_title || "Untitled survey"}
                      />
                      <MetaCard
                        label="Question count"
                        value={String(latestRun.result.question_count ?? 0)}
                      />
                    </div>

                    {runDebugSummary ? (
                      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        <MetaCard
                          label="Truly live answers"
                          value={String(runDebugSummary.truly_live_answers ?? 0)}
                        />
                        <MetaCard
                          label="Fallback answers"
                          value={String(runDebugSummary.fallback_answers ?? 0)}
                        />
                        <MetaCard
                          label="Provider errors"
                          value={String(runDebugSummary.provider_error_count ?? 0)}
                        />
                        <MetaCard
                          label="ML persona completion"
                          value={
                            runDebugSummary.ml_persona_completion_enabled ? "Enabled" : "Disabled"
                          }
                        />
                      </div>
                    ) : null}

                    {latestRunWarnings.length > 0 || latestParseWarnings.length > 0 ? (
                      <div className="mt-5 grid gap-4 xl:grid-cols-2">
                        {latestRunWarnings.length > 0 ? (
                          <WarningListPanel
                            title="Run warnings"
                            items={latestRunWarnings}
                          />
                        ) : null}
                        {latestParseWarnings.length > 0 ? (
                          <WarningListPanel
                            title="Survey parser notes"
                            items={latestParseWarnings}
                          />
                        ) : null}
                      </div>
                    ) : null}

                    <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                      <Button
                        variant="secondary"
                        onClick={() => scrollToSection("analysis")}
                      >
                        Continue to Analysis
                      </Button>
                      <Button variant="secondary" onClick={() => scrollToSection("analysis")}>
                        Inspect Details
                      </Button>
                    </div>
                  </>
                ) : latestRun.error ? (
                  <StatusBanner
                    tone="error"
                    message={
                      typeof latestRun.error.message === "string"
                        ? latestRun.error.message
                        : "The latest simulation run failed."
                    }
                    compact
                  />
                ) : null}
              </div>
            </GlassPanel>
          ) : null}

          {latestRun?.result ? (
            <>
              <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <BadgeChip tone="gold">Generated Personas</BadgeChip>
                  <BadgeChip>{`${latestRun.result.personas?.length ?? 0} personas`}</BadgeChip>
                </div>
                  <p className="mt-4 text-sm leading-6 text-app-muted">
                    This is the payoff of the setup flow: the grounded personas that shaped the study run.
                  </p>

                  <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="text-sm text-app-muted">
                      {buildPaginationLabel(
                        allPersonas.length,
                        personaPage,
                        PERSONAS_PER_PAGE,
                        "persona"
                      )}
                    </div>
                    <PagerControls
                      page={personaPage}
                      pageCount={personaPageCount}
                      onPrev={() => setPersonaPage((current) => Math.max(current - 1, 0))}
                      onNext={() =>
                        setPersonaPage((current) =>
                          Math.min(current + 1, personaPageCount - 1)
                        )
                      }
                    />
                  </div>

                  <div className="mt-5 grid gap-4 xl:grid-cols-2">
                    {personaPreviewRows.length > 0 ? (
                      personaPreviewRows.map((persona, index) => (
                        <PersonaPreviewCard
                          key={String(persona.persona_id ?? `${personaPage}-${index}`)}
                          persona={persona}
                          index={personaPage * PERSONAS_PER_PAGE + index}
                        />
                      ))
                    ) : (
                      <EmptyPanel message="No persona preview rows were returned with this run." />
                    )}
                  </div>
                </div>
              </GlassPanel>

              <GlassPanel className="p-5 sm:p-6">
                <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <BadgeChip tone="gold">Stability Check</BadgeChip>
                    <BadgeChip>Secondary module</BadgeChip>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-app-muted">
                    Use this lightweight repeatability check after the main run. It should not visually compete with the primary run CTA.
                  </p>

                  <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                    <NumberStepper
                      label="Repeat runs"
                      value={repeatRuns}
                      min={2}
                      max={5}
                      onChange={setRepeatRuns}
                    />
                    <Button
                      variant="secondary"
                      onClick={handleRunStabilityCheck}
                      disabled={isRunningStability}
                    >
                      {isRunningStability ? "Running Stability Check..." : "Run Stability Check"}
                    </Button>
                  </div>

                  <div className="mt-5">
                    <StatusBanner
                      tone={stabilityStatus.tone}
                      message={stabilityStatus.message}
                      compact
                    />
                  </div>

                  {stabilityRows.length > 0 ? (
                    <div className="mt-5 rounded-[1.35rem] border border-white/8 bg-white/[0.03] p-4">
                      <StabilityTable rows={stabilityRows} />
                    </div>
                  ) : null}
                </div>
              </GlassPanel>

              <GlassPanel className="p-5 sm:p-6">
                <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <BadgeChip tone="gold">Response Record Preview</BadgeChip>
                  <BadgeChip>{`${latestRun.result.response_records?.length ?? 0} records saved`}</BadgeChip>
                </div>
                  <p className="mt-4 text-sm leading-6 text-app-muted">
                    Keep the run chapter launch-oriented. You can page through the saved responses here, but Analysis is still the right place for deeper inspection.
                  </p>

                  <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="text-sm text-app-muted">
                      {buildPaginationLabel(
                        allResponseRecords.length,
                        responseRecordPage,
                        RESPONSE_RECORDS_PER_PAGE,
                        "record"
                      )}
                    </div>
                    <PagerControls
                      page={responseRecordPage}
                      pageCount={responseRecordPageCount}
                      onPrev={() =>
                        setResponseRecordPage((current) => Math.max(current - 1, 0))
                      }
                      onNext={() =>
                        setResponseRecordPage((current) =>
                          Math.min(current + 1, responseRecordPageCount - 1)
                        )
                      }
                    />
                  </div>

                  <div className="mt-5 space-y-3">
                    {recordPreviewRows.length > 0 ? (
                      recordPreviewRows.map((record, index) => (
                        <ResponseRecordCard
                          key={`${String(record.respondent_id ?? index)}-${String(record.question_id ?? index)}-${responseRecordPage}`}
                          record={record}
                          index={responseRecordPage * RESPONSE_RECORDS_PER_PAGE + index}
                        />
                      ))
                    ) : (
                      <EmptyPanel message="No response preview rows were returned with this run." />
                    )}
                  </div>
                </div>
              </GlassPanel>
            </>
          ) : null}
        </div>

        <div className="min-w-0 lg:sticky lg:top-6 lg:w-full lg:max-w-[23rem] lg:justify-self-end xl:max-w-[25rem] 2xl:max-w-[29rem]">
          <div className="space-y-5">
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="cyan">Launch Snapshot</BadgeChip>
                  <BadgeChip tone={runReady ? "cyan" : "gold"}>
                    {runReady ? "Ready to run" : "Blocked"}
                  </BadgeChip>
                </div>
                <div className="mt-5 space-y-3">
                  <ReadinessRow
                    label="Setup"
                    value={runReady ? "Audience, Survey, and Experiment are saved." : readinessBanner.message}
                    tone={runReady ? "cyan" : "gold"}
                  />
                  <ReadinessRow
                    label="Optional context"
                    value={buildOptionalContextMessage(study)}
                    tone={
                      study?.product?.status === "saved" || study?.market?.status === "saved"
                        ? "cyan"
                        : "gold"
                    }
                  />
                  <ReadinessRow
                    label="Latest run"
                    value={
                      latestRun?.result
                        ? `${latestRun.result.total_generated_responses} responses generated under ${formatMode(latestRun.result.experiment_mode)}.`
                        : "No saved run yet."
                    }
                    tone={latestRun?.result ? "cyan" : "gold"}
                  />
                </div>
              </div>
            </GlassPanel>

            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-white/5 bg-[linear-gradient(180deg,rgba(12,18,22,0.84),rgba(12,18,22,0.6))] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="gold">Execution Story</BadgeChip>
                </div>
                <p className="mt-4 text-sm leading-7 text-app-text">
                  {latestRun?.result
                    ? buildExecutionNarrative(latestRun.result)
                    : "When you run the study, the backend will generate grounded personas, answer the normalized survey through the configured execution plan, and save a result that can flow into Analysis."}
                </p>
              </div>
            </GlassPanel>
          </div>
        </div>
      </div>
    </SectionWrapper>
  );
}

function buildRunStatus(
  latestRun: SimulationJobPayload<SimulationRunResultPayload> | null,
  study: unknown
): StatusState {
  if (latestRun?.status === "completed" && latestRun.result) {
    const warningCount = latestRun.result.warnings?.length ?? 0;
    if (warningCount > 0) {
      return {
        tone: "warning",
        message: `Run completed with ${warningCount} warning${warningCount === 1 ? "" : "s"}. Review the trust conditions and result summary before moving to Analysis.`,
      };
    }
    return {
      tone: "success",
      message: "Run completed successfully and the latest result is loaded from backend state.",
    };
  }

  if (latestRun?.status === "failed") {
    return {
      tone: "error",
      message:
        typeof latestRun.error?.message === "string"
          ? latestRun.error.message
          : "The latest run failed. Review the setup and try again.",
    };
  }

  return buildReadinessBanner(study);
}

function buildStabilityStatus(
  latestStabilityCheck: SimulationJobPayload<SimulationStabilityResultPayload> | null
): StatusState {
  if (!latestStabilityCheck?.result) {
    return {
      tone: "neutral",
      message: "Run the main study first, then use Stability Check as a lightweight repeatability pass.",
    };
  }

  const unstableCount =
    latestStabilityCheck.result.stability_labels?.filter((label) => label === "unstable")
      .length ?? 0;
  if (unstableCount > 0) {
    return {
      tone: "warning",
      message: `Stability check completed with ${unstableCount} unstable metric${unstableCount === 1 ? "" : "s"}.`,
    };
  }

  return {
    tone: "success",
    message: "Stability check completed and saved.",
  };
}

function buildReadinessBanner(study: any): StatusState {
  const missing: string[] = [];
  if (study?.audience?.status !== "saved") {
    missing.push("Audience");
  }
  if (study?.survey?.status !== "saved") {
    missing.push("Survey");
  }
  if (study?.experiment?.status !== "saved") {
    missing.push("Experiment");
  }

  if (missing.length > 0) {
    return {
      tone: "warning",
      message: `The study is not ready to run yet. Save ${missing.join(", ")} first.`,
    };
  }

  return {
    tone: "success",
    message:
      "The core execution stack is saved. Product and Market context will further shape the run when available, but the study is ready to launch now.",
  };
}

function isReadyToRun(study: any) {
  return (
    study?.audience?.status === "saved" &&
    study?.survey?.status === "saved" &&
    study?.experiment?.status === "saved"
  );
}

function buildPredictedRunConditions(study: any): SimulationRunConditions {
  const latestPreview = study?.derived?.latest_persona_preview;
  const audienceValue = study?.audience?.value;
  const experimentValue = study?.experiment?.value;
  const hasZip = Boolean(audienceValue?.zip_code);
  const hasProduct = study?.product?.status === "saved";
  const hasMarket = study?.market?.status === "saved";

  return {
    context_influence: {
      enabled: true,
      sources: ["audience", ...(hasProduct ? ["product"] : []), ...(hasMarket ? ["market"] : [])],
    },
    geography_aware_priors: {
      status: latestPreview?.geography_context?.puma
        ? "enabled"
        : hasZip
          ? "degraded"
          : "global",
      detail: latestPreview?.geography_context?.puma
        ? "Latest persona preview resolved ZIP-based geography context."
        : hasZip
          ? "A ZIP filter exists, but the next run may still fall back to global tables if geography context cannot be resolved."
          : "No ZIP filter is saved, so geography-aware priors remain global.",
    },
    grounded_priors: {
      status:
        latestPreview?.grounded_priors_available === true
          ? "enabled"
          : latestPreview?.grounded_priors_available === false
            ? "degraded"
            : "unknown",
      detail:
        latestPreview?.grounded_priors_available === true
          ? "Latest persona preview confirms grounded priors are available."
          : latestPreview?.grounded_priors_available === false
            ? "Latest persona preview indicates grounded priors are unavailable."
            : "Grounded priors will resolve when the run begins.",
    },
    affordability_priors: {
      status:
        latestPreview?.cex_affordability_available === true
          ? "enabled"
          : latestPreview?.cex_affordability_available === false
            ? "degraded"
            : "unknown",
      detail:
        latestPreview?.cex_affordability_available === true
          ? "Latest persona preview confirms affordability priors are available."
          : latestPreview?.cex_affordability_available === false
            ? "Latest persona preview indicates affordability priors are unavailable."
            : "Affordability priors will resolve when the run begins.",
    },
    generation_mode: "auto",
    selected_models: experimentValue?.selected_models ?? [],
  };
}

function buildOptionalContextMessage(study: any) {
  const available = [
    study?.product?.status === "saved" ? "Product" : null,
    study?.market?.status === "saved" ? "Market" : null,
  ].filter(Boolean) as string[];

  if (available.length === 0) {
    return "Only audience + survey + experiment are guaranteed right now; product and market framing are still optional in the current backend contract.";
  }

  return `${available.join(" and ")} framing will influence the run alongside the audience.`;
}

function buildExecutionNarrative(result: SimulationRunResultPayload) {
  return `${formatMode(result.experiment_mode)} generated ${result.total_generated_responses} responses across ${summarizeList(
    result.models_used ?? [],
    2
  )}, using ${formatGenerationMode(result.generation_mode)} with ${result.personas?.length ?? 0} grounded persona${(result.personas?.length ?? 0) === 1 ? "" : "s"}.`;
}

function summarizeList(values: string[], maxVisible: number) {
  if (values.length === 0) {
    return "none";
  }
  const visible = values.slice(0, maxVisible);
  if (values.length <= maxVisible) {
    return visible.join(", ");
  }
  return `${visible.join(", ")}, +${values.length - maxVisible} more`;
}

function formatMode(mode?: string | null) {
  if (mode === "split") {
    return "Split Sample";
  }
  if (mode === "mirror") {
    return "Mirror Sample";
  }
  if (mode === "stability") {
    return "Stability Sample";
  }
  return mode || "Unknown";
}

function formatGenerationMode(mode?: string | null) {
  if (mode === "openrouter_live") {
    return "OpenRouter Live";
  }
  if (mode === "mock") {
    return "Mock fallback";
  }
  if (mode === "auto") {
    return "Auto-resolve at run time";
  }
  return mode || "Unknown";
}

function formatAnswer(answer: unknown) {
  if (Array.isArray(answer)) {
    return answer.map((value) => String(value)).join(" • ");
  }
  if (answer === null || typeof answer === "undefined") {
    return "No answer recorded.";
  }
  return String(answer);
}

function TrustConditionCard({
  title,
  status,
  detail,
}: {
  title: string;
  status: string;
  detail: string;
}) {
  const tone =
    status === "enabled" ? "cyan" : status === "global" ? "neutral" : status === "unknown" ? "neutral" : "gold";
  return (
    <div className="rounded-[1.3rem] border border-white/8 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeChip>{title}</BadgeChip>
        <BadgeChip tone={tone}>{status.replaceAll("_", " ")}</BadgeChip>
      </div>
      <p className="mt-3 text-sm leading-6 text-app-muted">{detail}</p>
    </div>
  );
}

function StatusBanner({
  tone,
  message,
  compact = false,
}: {
  tone: StatusTone;
  message: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-[1.35rem] border px-4 py-3 text-sm leading-6",
        !compact && "sm:px-5 sm:py-4",
        tone === "success" &&
          "border-app-cyan/20 bg-[rgba(15,216,255,0.08)] text-app-cyan",
        tone === "warning" &&
          "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
        tone === "error" &&
          "border-app-gold/20 bg-[rgba(216,186,103,0.08)] text-app-gold",
        tone === "neutral" &&
          "border-white/8 bg-white/[0.03] text-app-muted"
      )}
    >
      {message}
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

function PersonaPreviewCard({
  persona,
  index,
}: {
  persona: Record<string, unknown>;
  index: number;
}) {
  const subtitle = [
    toOptionalString(persona.segment_label),
    toOptionalString(persona.fit_tier),
  ]
    .filter(Boolean)
    .join(" • ");
  const traits = [
    toOptionalString(persona.age_bucket) || toOptionalString(persona.age_band),
    toOptionalString(persona.income_bucket) || toOptionalString(persona.income_band),
    toOptionalString(persona.home_type),
    toOptionalString(persona.work_mode),
  ].filter(Boolean);

  return (
    <div className="rounded-[1.35rem] border border-white/8 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-app-text">
            {toOptionalString(persona.persona_id) || `Persona ${index + 1}`}
          </div>
          <div className="mt-1 text-sm text-app-muted">
            {subtitle || "Grounded persona preview"}
          </div>
        </div>
        <BadgeChip>{`P${index + 1}`}</BadgeChip>
      </div>
      <p className="mt-3 text-sm leading-6 text-app-muted">
        {traits.length > 0 ? traits.join(" • ") : "Persona traits unavailable."}
      </p>
    </div>
  );
}

function ResponseRecordCard({
  record,
  index,
}: {
  record: Record<string, unknown>;
  index: number;
}) {
  const respondentId = toOptionalString(record.respondent_id) || `Resp ${index + 1}`;
  const model = toOptionalString(record.model) || "model";
  const questionId = toOptionalString(record.question_id) || "Q";
  const questionText = prettifyQuestionText(record.question_text);
  const answer = formatAnswer(record.answer);

  return (
    <div className="rounded-[1.2rem] border border-white/6 bg-black/10 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeChip>{respondentId}</BadgeChip>
        <BadgeChip>{model}</BadgeChip>
        <BadgeChip tone="neutral">{questionId}</BadgeChip>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,0.9fr)]">
        <div className="rounded-[1rem] border border-white/6 bg-white/[0.03] p-4">
          <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
            Question
          </div>
          <div className="mt-2 text-sm leading-7 text-app-text">
            {questionText || "Question text unavailable."}
          </div>
        </div>

        <div className="rounded-[1rem] border border-app-cyan/10 bg-[rgba(15,216,255,0.04)] p-4">
          <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
            Answer
          </div>
          <div className="mt-2 text-sm leading-7 text-app-text">{answer}</div>
        </div>
      </div>
    </div>
  );
}

function StabilityTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const runColumns = Array.from(
    new Set(
      rows.flatMap((row) =>
        Object.keys(row).filter((key) => key.startsWith("run_"))
      )
    )
  ).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-y-3">
        <thead>
          <tr className="text-left">
            <th className="px-3 pb-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
              Metric
            </th>
            <th className="px-3 pb-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
              Status
            </th>
            {runColumns.map((column) => (
              <th
                key={column}
                className="px-3 pb-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted"
              >
                {humanizeRunColumn(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${String(row.metric_name ?? index)}-${index}`}>
              <td className="rounded-l-[1rem] border border-white/6 border-r-0 bg-black/10 px-3 py-3 text-sm text-app-text">
                {humanizeMetricName(row.metric_name, index)}
              </td>
              <td className="border border-white/6 border-l-0 border-r-0 bg-black/10 px-3 py-3">
                <BadgeChip
                  tone={
                    row.stability_label === "stable"
                      ? "cyan"
                      : row.stability_label === "mostly_stable"
                        ? "gold"
                        : "gold"
                  }
                >
                  {humanizeToken(toOptionalString(row.stability_label) || "unknown")}
                </BadgeChip>
              </td>
              {runColumns.map((column, runIndex) => (
                <td
                  key={`${String(row.metric_name ?? index)}-${column}`}
                  className={cn(
                    "border border-white/6 border-l-0 bg-black/10 px-3 py-3 text-sm leading-6 text-app-muted",
                    runIndex === runColumns.length - 1 && "rounded-r-[1rem]"
                  )}
                >
                  {formatTableValue(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WarningListPanel({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <div className="rounded-[1.35rem] border border-app-gold/20 bg-[rgba(216,186,103,0.08)] p-4">
      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-gold">
        {title}
      </div>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-app-muted">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function PagerControls({
  page,
  pageCount,
  onPrev,
  onNext,
}: {
  page: number;
  pageCount: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="inline-flex items-center gap-3 rounded-[1.2rem] border border-white/8 bg-white/[0.03] px-3 py-2">
      <button
        type="button"
        onClick={onPrev}
        disabled={page <= 0}
        className={cn(
          "inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/8 bg-black/10 text-app-text transition",
          page <= 0
            ? "cursor-not-allowed opacity-40"
            : "hover:border-app-cyan/25 hover:text-app-cyan"
        )}
      >
        ←
      </button>
      <span className="min-w-[4.5rem] text-center text-sm text-app-muted">
        {pageCount === 0 ? "0 / 0" : `${page + 1} / ${pageCount}`}
      </span>
      <button
        type="button"
        onClick={onNext}
        disabled={page >= pageCount - 1}
        className={cn(
          "inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/8 bg-black/10 text-app-text transition",
          page >= pageCount - 1
            ? "cursor-not-allowed opacity-40"
            : "hover:border-app-cyan/25 hover:text-app-cyan"
        )}
      >
        →
      </button>
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

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="rounded-[1.35rem] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8 text-sm leading-6 text-app-muted">
      {message}
    </div>
  );
}

function NumberStepper({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="inline-flex items-center gap-3 rounded-[1.2rem] border border-white/8 bg-white/[0.03] px-3 py-2">
      <span className="text-sm text-app-muted">{label}</span>
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/8 bg-black/10 text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan"
      >
        −
      </button>
      <span className="w-6 text-center text-sm text-app-text">{value}</span>
      <button
        type="button"
        onClick={() => onChange(Math.min(max, value + 1))}
        className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/8 bg-black/10 text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan"
      >
        +
      </button>
    </div>
  );
}

function toOptionalString(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function paginateItems<T>(items: T[], page: number, pageSize: number) {
  const start = page * pageSize;
  return items.slice(start, start + pageSize);
}

function buildPaginationLabel(
  total: number,
  page: number,
  pageSize: number,
  noun: string
) {
  if (total === 0) {
    return `No ${noun}s available.`;
  }
  const start = page * pageSize + 1;
  const end = Math.min(total, start + pageSize - 1);
  return `Showing ${start}-${end} of ${total} ${noun}${total === 1 ? "" : "s"}`;
}

function prettifyQuestionText(value: unknown) {
  const text = toOptionalString(value);
  if (!text) {
    return null;
  }
  return text
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
}

function humanizeMetricName(value: unknown, index: number) {
  const label = toOptionalString(value);
  if (!label) {
    return `Metric ${index + 1}`;
  }
  return humanizeToken(label);
}

function humanizeRunColumn(value: string) {
  return value.replace("run_", "Run ");
}

function humanizeToken(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatTableValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((entry) => String(entry)).join(" • ");
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (value === null || typeof value === "undefined" || value === "") {
    return "n/a";
  }
  return String(value).replaceAll("_", " ");
}
