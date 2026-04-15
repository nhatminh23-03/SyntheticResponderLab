"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  AnalysisDistributionRow,
  AnalysisPayload,
  AnalysisResponseRecord,
  getAnalysis,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { SelectInput } from "@/components/ui/form-controls";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";

const RECORDS_PER_PAGE = 12;

type StatusTone = "neutral" | "success" | "warning" | "error";

type StatusState = {
  tone: StatusTone;
  message: string;
};

const EMPTY_STATUS: StatusState = {
  tone: "neutral",
  message: "Analysis loads after a run is completed and saved.",
};

export function AnalysisSection() {
  const { studyId, study } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [status, setStatus] = useState<StatusState>(EMPTY_STATUS);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedQuestionId, setSelectedQuestionId] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState("All");
  const [selectedSegment, setSelectedSegment] = useState("All");
  const [recordsPage, setRecordsPage] = useState(0);

  useEffect(() => {
    setRecordsPage(0);
  }, [selectedQuestionId, selectedModel, selectedSegment]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateAnalysis() {
      if (!studyId) {
        if (!cancelled) {
          setAnalysis(null);
          setStatus(EMPTY_STATUS);
        }
        return;
      }

      setIsLoading(true);
      try {
        const result = await getAnalysis(studyId, {
          questionId: selectedQuestionId,
          model: selectedModel,
          segment: selectedSegment,
          recordsLimit: RECORDS_PER_PAGE,
          recordsOffset: recordsPage * RECORDS_PER_PAGE,
          openTextLimit: 8,
        });

        if (cancelled) {
          return;
        }

        setAnalysis(result);
        setSelectedQuestionId(result.filters?.selected_question_id ?? null);
        setSelectedModel(result.filters?.selected_model ?? "All");
        setSelectedSegment(result.filters?.selected_segment ?? "All");
        setStatus(
          result.available
            ? {
                tone: "success",
                message:
                  "Analysis is loaded from the latest run. Confidence and agreement labels are directional heuristics, not final proof.",
              }
            : {
                tone: "warning",
                message:
                  result.message ??
                  "No analysis payload is available yet. Run the study first.",
              }
        );
      } catch (error) {
        if (!cancelled) {
          setStatus({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Unable to load analysis right now.",
          });
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void hydrateAnalysis();

    return () => {
      cancelled = true;
    };
  }, [studyId, study?.updated_at, selectedQuestionId, selectedModel, selectedSegment, recordsPage]);

  const questionOptions = analysis?.filters?.question_options ?? [];
  const modelOptions = analysis?.filters?.model_options ?? ["All"];
  const segmentOptions = analysis?.filters?.segment_options ?? ["All"];
  const questionExplorer = analysis?.question_explorer;
  const distributionRows = questionExplorer?.distribution ?? [];
  const recordsPreview = analysis?.records_preview;
  const recordsTotal = recordsPreview?.total ?? 0;
  const recordPageCount = recordsTotal > 0 ? Math.ceil(recordsTotal / RECORDS_PER_PAGE) : 0;
  const benchmark = analysis?.benchmark_snapshot;
  const realism = analysis?.realism_scorecard;
  const run = analysis?.run;
  const runDebugSummary = analysis?.run_debug_summary;
  const runWarnings = analysis?.context_notes?.run_warnings ?? [];
  const surveyWarnings = analysis?.context_notes?.survey_parse_warnings ?? [];
  const openTextSamples = analysis?.open_text?.samples ?? [];
  const openTextQuestion = useMemo(() => {
    const selectedId = analysis?.open_text?.selected_question_id;
    return analysis?.open_text?.question_options?.find((entry) => entry.id === selectedId) ?? null;
  }, [analysis?.open_text]);

  return (
    <SectionWrapper id="analysis" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1.03fr)_24rem] 2xl:grid-cols-[minmax(0,1.04fr)_29rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={8}
              eyebrow="Analysis"
              title="Read what happened in the run and how trustworthy each signal is."
              description="Start with summary cards, then inspect question-level evidence before carrying signals into Insights."
            />
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <div className="rounded-[1.45rem] border [border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] px-5 py-4 text-sm leading-6 text-app-gold">
              {analysis?.transparency_note ??
                "Transparency note: confidence and agreement labels are rule-based summaries to speed interpretation."}
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.06}>
            <StatusBanner tone={status.tone} message={status.message} />
          </RevealOnScroll>

          {!analysis?.available ? (
            <GlassPanel className="p-6 sm:p-7">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-6">
                <div className="flex flex-wrap gap-3">
                  <BadgeChip tone="gold">Analysis Unavailable</BadgeChip>
                  {run?.status ? <BadgeChip>{run.status}</BadgeChip> : null}
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-app-muted">
                  {analysis?.message ??
                    "No saved run is available yet. Complete Run Simulation first, then return here for summary patterns, trust framing, and question-level evidence."}
                </p>
                <div className="mt-5">
                  <Button variant="secondary" onClick={() => scrollToSection("run-simulation")}>
                    Return to Run Simulation
                  </Button>
                </div>
              </div>
            </GlassPanel>
          ) : (
            <>
              <RevealOnScroll delay={0.08}>
                <details className="rounded-[1.55rem] border border-app-border [background:var(--status-neutral-bg)] p-5">
                  <summary className="cursor-pointer list-none text-sm font-medium text-app-text">
                    Context & Study Inputs
                  </summary>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <ContextSummaryCard
                      label="Run"
                      value={
                        [
                          run?.run_id,
                          run?.survey_title,
                          run?.experiment_mode ? formatMode(run.experiment_mode) : null,
                        ]
                          .filter(Boolean)
                          .join(" • ") || "No run metadata"
                      }
                    />
                    <ContextSummaryCard
                      label="Workflow"
                      value={
                        study?.derived?.workflow?.ready_for_persona_preview
                          ? "All setup sections were saved before this run."
                          : "Run completed with partial setup; interpret outputs more cautiously."
                      }
                    />
                    <ContextSummaryCard
                      label="Audience"
                      value={buildAudienceAnchor(study?.audience?.value)}
                    />
                    <ContextSummaryCard
                      label="Product & Market"
                      value={buildProductMarketAnchor(study)}
                    />
                  </div>
                </details>
              </RevealOnScroll>

              <RevealOnScroll delay={0.1}>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                  <SummaryKpiCard
                    label="Responses Analyzed"
                    value={String(analysis.summary?.total_records ?? 0)}
                  />
                  <SummaryKpiCard
                    label="Unique Personas"
                    value={String(analysis.summary?.unique_respondents ?? 0)}
                  />
                  <SummaryKpiCard
                    label="Questions Covered"
                    value={String(analysis.summary?.question_count ?? 0)}
                  />
                  <SummaryKpiCard
                    label="Models Compared"
                    value={String(analysis.summary?.models_present?.length ?? 0)}
                  />
                  <SummaryKpiCard
                    label="Segment Coverage"
                    value={analysis.summary?.active_segment_summary ?? "No segment labels"}
                  />
                </div>
              </RevealOnScroll>

              <RevealOnScroll delay={0.12}>
                <div className="grid gap-4 xl:grid-cols-2">
                  <TrustBandCard
                    title="Benchmark Snapshot"
                    tone={benchmark?.available ? "cyan" : "gold"}
                    body={
                      benchmark?.available
                        ? `Consistency snapshot: ${benchmark.stability_summary}. Top repeated use case: ${benchmark.top_use_case_consensus ?? "n/a"}. Top repeated barrier: ${benchmark.top_barrier_consensus ?? "n/a"}.`
                        : benchmark?.message ?? "Benchmark snapshot is unavailable."
                    }
                  >
                    {benchmark?.available ? (
                      <details className="mt-4 rounded-[1.15rem] border border-app-border [background:var(--status-neutral-bg)] p-3">
                        <summary className="cursor-pointer list-none text-sm text-app-text">
                          Show detailed benchmark table
                        </summary>
                        <div className="mt-3 overflow-x-auto">
                          <CompactTable rows={benchmark.detailed_table ?? []} />
                        </div>
                      </details>
                    ) : null}
                  </TrustBandCard>

                  <TrustBandCard
                    title="Neo Realism Scorecard"
                    tone={realism?.available ? "cyan" : "gold"}
                    body={
                      realism?.available
                        ? buildRealismSummary(realism.summary)
                        : realism?.message ?? "Realism scorecard unavailable."
                    }
                  >
                    {realism?.available ? (
                      <details className="mt-4 rounded-[1.15rem] border border-app-border [background:var(--status-neutral-bg)] p-3">
                        <summary className="cursor-pointer list-none text-sm text-app-text">
                          Show detailed realism table
                        </summary>
                        <div className="mt-3 overflow-x-auto">
                          <CompactTable rows={realism.question_rows ?? []} />
                        </div>
                      </details>
                    ) : null}
                  </TrustBandCard>

                  <TrustBandCard
                    title="Confidence"
                    tone={confidenceTone(questionExplorer?.trust?.confidence_label)}
                    body={questionExplorer?.trust?.confidence_label ?? "Needs validation"}
                  >
                    <p className="mt-3 text-sm leading-6 text-app-muted">
                      {questionExplorer?.trust?.explanation ??
                        "Confidence updates after you select a question and filters."}
                    </p>
                  </TrustBandCard>

                  <TrustBandCard
                    title="Model Agreement"
                    tone={agreementTone(questionExplorer?.trust?.agreement_label)}
                    body={questionExplorer?.trust?.agreement_label ?? "Partial agreement"}
                  >
                    <p className="mt-3 text-sm leading-6 text-app-muted">
                      Agreement is a heuristic read of how aligned models are under current filters.
                    </p>
                  </TrustBandCard>
                </div>
              </RevealOnScroll>

              <RevealOnScroll delay={0.14}>
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                    <div className="flex flex-wrap items-center gap-3">
                      <BadgeChip tone="cyan">Question Explorer</BadgeChip>
                      <BadgeChip>{`${analysis.filters?.filtered_record_count ?? 0} records match filters`}</BadgeChip>
                    </div>

                    <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(13rem,0.8fr)_minmax(13rem,0.8fr)]">
                      <SelectBlock
                        label="Question"
                        value={selectedQuestionId ?? ""}
                        onChange={(value) => setSelectedQuestionId(value)}
                        options={questionOptions.map((question) => ({
                          label: `${question.id} — ${question.text}`,
                          value: question.id,
                        }))}
                      />
                      <SelectBlock
                        label="Model"
                        value={selectedModel}
                        onChange={setSelectedModel}
                        options={modelOptions.map((entry) => ({
                          label: entry,
                          value: entry,
                        }))}
                      />
                      <SelectBlock
                        label="Segment"
                        value={selectedSegment}
                        onChange={setSelectedSegment}
                        options={segmentOptions.map((entry) => ({
                          label: entry,
                          value: entry,
                        }))}
                      />
                    </div>

                    <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1.04fr)_minmax(20rem,0.96fr)]">
                      <div className="space-y-4">
                        <div className="rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
                          <div className="flex flex-wrap gap-2">
                            <BadgeChip>{questionExplorer?.question_id ?? "No question"}</BadgeChip>
                            <BadgeChip tone="neutral">
                              {formatQuestionType(questionExplorer?.question_type)}
                            </BadgeChip>
                            <BadgeChip>{`${questionExplorer?.response_count ?? 0} responses`}</BadgeChip>
                          </div>
                          <h3 className="mt-4 text-lg font-medium leading-8 text-app-text">
                            {questionExplorer?.question_text ?? "No question selected."}
                          </h3>

                          <div className="mt-4 grid gap-3 sm:grid-cols-3">
                            <MetaMiniCard
                              label="Top Answer"
                              value={String(questionExplorer?.stats_summary?.top_answer ?? "n/a")}
                            />
                            <MetaMiniCard
                              label="Top Share"
                              value={
                                questionExplorer?.stats_summary?.top_percentage !== undefined
                                  ? `${String(questionExplorer?.stats_summary?.top_percentage)}%`
                                  : "n/a"
                              }
                            />
                            <MetaMiniCard
                              label="Average"
                              value={String(questionExplorer?.stats_summary?.average_value ?? "n/a")}
                            />
                          </div>
                        </div>

                        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
                          <DistributionChart rows={distributionRows} />
                          <DistributionTable rows={distributionRows} />
                        </div>
                      </div>

                      <div className="rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
                        <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
                          Question Trust Note
                        </div>
                        <p className="mt-3 text-sm leading-7 text-app-text">
                          {questionExplorer?.trust?.explanation ??
                            "Trust explanation will appear once the selected question has enough evidence."}
                        </p>
                      </div>
                    </div>
                  </div>
                </GlassPanel>
              </RevealOnScroll>

              <RevealOnScroll delay={0.16}>
                <div className="grid gap-4 xl:grid-cols-2">
                  <GlassPanel className="p-5 sm:p-6">
                    <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="gold">Open Text Evidence</BadgeChip>
                        {openTextQuestion ? (
                          <BadgeChip>{openTextQuestion.id}</BadgeChip>
                        ) : (
                          <BadgeChip>No open-text samples</BadgeChip>
                        )}
                      </div>
                      <p className="mt-4 text-sm leading-6 text-app-muted">
                        {openTextQuestion
                          ? openTextQuestion.text
                          : "No open-text question is available under the active filters."}
                      </p>

                      <div className="mt-5 space-y-3">
                        {openTextSamples.length > 0 ? (
                          openTextSamples.map((sample, index) => (
                            <EvidenceCard
                              key={`${String(sample.respondent_id ?? index)}-${String(sample.model ?? index)}`}
                              header={`${String(sample.respondent_id ?? `Resp ${index + 1}`)} • ${String(sample.model ?? "model")}`}
                              body={formatAnswer(sample.answer)}
                              subtext={String(sample.segment_label ?? "Unsegmented")}
                            />
                          ))
                        ) : (
                          <EmptyState message="No open-text responses match the active filters." />
                        )}
                      </div>
                    </div>
                  </GlassPanel>

                  <GlassPanel className="p-5 sm:p-6">
                    <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="gold">Run Notes</BadgeChip>
                      </div>

                      <div className="mt-5 space-y-3">
                        {runWarnings.length > 0 ? (
                          <EvidenceList
                            title="Run notes"
                            items={runWarnings}
                            tone="gold"
                          />
                        ) : null}
                        {surveyWarnings.length > 0 ? (
                          <EvidenceList
                            title="Survey parsing notes"
                            items={surveyWarnings}
                            tone="neutral"
                          />
                        ) : null}
                        {runWarnings.length === 0 && surveyWarnings.length === 0 ? (
                          <EmptyState message="No run notes or survey parsing notes were attached to the latest result." />
                        ) : null}
                      </div>
                    </div>
                  </GlassPanel>
                </div>
              </RevealOnScroll>

              <RevealOnScroll delay={0.18}>
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <BadgeChip tone="gold">Full Records Preview</BadgeChip>
                          <BadgeChip>{`${recordsTotal} records`}</BadgeChip>
                        </div>
                        <p className="mt-3 text-sm leading-6 text-app-muted">
                          Use this as raw evidence from the latest run result. For interpretation and decisions, continue to Insights.
                        </p>
                      </div>
                      <PagerControls
                        page={recordsPage}
                        pageCount={recordPageCount}
                        onPrev={() => setRecordsPage((current) => Math.max(current - 1, 0))}
                        onNext={() =>
                          setRecordsPage((current) => Math.min(current + 1, Math.max(recordPageCount - 1, 0)))
                        }
                      />
                    </div>

                    <div className="mt-5 overflow-x-auto">
                      <RecordsPreviewTable rows={recordsPreview?.rows ?? []} />
                    </div>
                  </div>
                </GlassPanel>
              </RevealOnScroll>
            </>
          )}
        </div>

        <RevealOnScroll delay={0.08} className="min-w-0 lg:sticky lg:top-6 lg:w-full lg:max-w-[22rem] lg:justify-self-end xl:max-w-[24rem] 2xl:max-w-[29rem]">
          <div className="space-y-5">
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="cyan">Run Snapshot</BadgeChip>
                  {isLoading ? <BadgeChip>Refreshing</BadgeChip> : null}
                </div>
                <div className="mt-5 space-y-3">
                  <SidebarRow
                    label="Run ID"
                    value={run?.run_id ?? "No saved run"}
                  />
                  <SidebarRow
                    label="Status"
                    value={run?.status ?? "Unavailable"}
                  />
                  <SidebarRow
                    label="Survey"
                    value={run?.survey_title ?? "Unavailable"}
                  />
                  <SidebarRow
                    label="Generated"
                    value={
                      run?.generated_responses !== undefined
                        ? `${run.generated_responses} responses`
                        : "Unavailable"
                    }
                  />
                  <SidebarRow
                    label="Live answers"
                    value={
                      runDebugSummary?.truly_live_answers !== undefined &&
                      runDebugSummary?.total_answers !== undefined
                        ? `${runDebugSummary.truly_live_answers}/${runDebugSummary.total_answers}`
                        : "Unavailable"
                    }
                  />
                  <SidebarRow
                    label="ML completion"
                    value={
                      runDebugSummary?.ml_persona_completion_enabled !== undefined
                        ? runDebugSummary.ml_persona_completion_enabled
                          ? "Enabled"
                          : "Disabled"
                        : "Unavailable"
                    }
                  />
                </div>
              </div>
            </GlassPanel>

            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="gold">Interpretation Frame</BadgeChip>
                </div>
                <p className="mt-4 text-sm leading-7 text-app-text">
                  Use this chapter to move from run output to interpretation: inspect the current question, check trust framing, review evidence, then carry signal into Insights.
                </p>
              </div>
            </GlassPanel>
          </div>
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}

function SelectBlock({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
}) {
  return (
    <div>
      <div className="mb-2 text-[0.72rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
      <SelectInput value={value} onChange={onChange} options={options} />
    </div>
  );
}

function SummaryKpiCard({ label, value }: { label: string; value: string }) {
  return (
    <GlassPanel className="p-4 sm:p-5">
      <div className="rounded-[1.3rem] border border-app-border [background:var(--theme-panel-gradient)] p-4">
        <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
          {label}
        </div>
        <div className="mt-2 text-lg font-medium text-app-text">{value}</div>
      </div>
    </GlassPanel>
  );
}

function TrustBandCard({
  title,
  tone,
  body,
  children,
}: {
  title: string;
  tone: "cyan" | "gold" | "neutral";
  body: string;
  children?: ReactNode;
}) {
  return (
    <GlassPanel className="p-5 sm:p-6">
      <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
        <div className="flex flex-wrap gap-2">
          <BadgeChip tone={tone}>{title}</BadgeChip>
        </div>
        <p className="mt-4 text-sm leading-7 text-app-text">{body}</p>
        {children}
      </div>
    </GlassPanel>
  );
}

function DistributionChart({ rows }: { rows: AnalysisDistributionRow[] }) {
  const maxCount = rows.reduce((highest, row) => Math.max(highest, row.count), 0);

  return (
    <div className="rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
        Answer Distribution
      </div>
      <div className="mt-4 space-y-3">
        {rows.length > 0 ? (
          rows.map((row) => (
            <div key={row.answer_display} className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-sm text-app-text">
                <span className="truncate">{row.answer_display}</span>
                <span className="shrink-0 text-app-muted">
                  {row.count} • {row.percentage}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-white/[0.05]">
                <div
                  className="h-2 rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.75),rgba(216,186,103,0.8))]"
                  style={{
                    width: `${maxCount > 0 ? (row.count / maxCount) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          ))
        ) : (
          <EmptyState message="No distribution is available for the current question/filter combination." />
        )}
      </div>
    </div>
  );
}

function DistributionTable({ rows }: { rows: AnalysisDistributionRow[] }) {
  return (
    <div className="rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
        Answer Summary
      </div>
      <div className="mt-4 overflow-hidden rounded-[1rem] border border-app-border">
        <table className="min-w-full divide-y divide-white/6 text-sm">
          <thead className="[background:var(--status-neutral-bg)] text-app-muted">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Answer</th>
              <th className="px-3 py-2 text-left font-medium">Count</th>
              <th className="px-3 py-2 text-left font-medium">Share</th>
            </tr>
          </thead>
          <tbody>
            {rows.length > 0 ? (
              rows.map((row) => (
                <tr key={row.answer_display} className="border-t border-app-border text-app-text">
                  <td className="px-3 py-2">{row.answer_display}</td>
                  <td className="px-3 py-2">{row.count}</td>
                  <td className="px-3 py-2">{row.percentage}%</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-4 text-app-muted" colSpan={3}>
                  No answer rows available.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EvidenceCard({
  header,
  body,
  subtext,
}: {
  header: string;
  body: string;
  subtext?: string;
}) {
  return (
    <div className="rounded-[1.2rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="text-sm font-medium text-app-text">{header}</div>
      {subtext ? <div className="mt-1 text-sm text-app-muted">{subtext}</div> : null}
      <p className="mt-3 text-sm leading-7 text-app-text">{body}</p>
    </div>
  );
}

function EvidenceList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "gold" | "neutral";
}) {
  return (
    <div
      className={cn(
        "rounded-[1.2rem] border p-4",
        tone === "gold"
          ? "border-app-gold/20 bg-[rgba(216,186,103,0.08)]"
          : "border-app-border [background:var(--status-neutral-bg)]"
      )}
    >
      <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
        {title}
      </div>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-app-text">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function RecordsPreviewTable({ rows }: { rows: AnalysisResponseRecord[] }) {
  return (
    <table className="min-w-full divide-y divide-white/6 text-sm">
      <thead className="text-app-muted">
        <tr>
          <th className="px-3 py-2 text-left font-medium">Respondent</th>
          <th className="px-3 py-2 text-left font-medium">Model</th>
          <th className="px-3 py-2 text-left font-medium">Question</th>
          <th className="px-3 py-2 text-left font-medium">Answer</th>
        </tr>
      </thead>
      <tbody>
        {rows.length > 0 ? (
          rows.map((row, index) => (
            <tr key={`${String(row.respondent_id ?? index)}-${String(row.question_id ?? index)}-${index}`} className="border-t border-app-border text-app-text">
              <td className="px-3 py-3 align-top">{String(row.respondent_id ?? "n/a")}</td>
              <td className="px-3 py-3 align-top">{String(row.model ?? "n/a")}</td>
              <td className="px-3 py-3 align-top">
                <div className="font-medium">{String(row.question_id ?? "Q")}</div>
                <div className="mt-1 max-w-[26rem] text-app-muted">
                  {prettifyQuestionText(row.question_text) ?? "Question unavailable"}
                </div>
              </td>
              <td className="px-3 py-3 align-top">{formatAnswer(row.answer)}</td>
            </tr>
          ))
        ) : (
          <tr>
            <td className="px-3 py-4 text-app-muted" colSpan={4}>
              No records match the current filters.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function CompactTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  if (rows.length === 0) {
    return <EmptyState message="No detailed rows are available." />;
  }

  return (
    <table className="min-w-full divide-y divide-white/6 text-sm">
      <thead className="text-app-muted">
        <tr>
          {columns.map((column) => (
            <th key={column} className="px-3 py-2 text-left font-medium">
              {humanizeToken(column)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index} className="border-t border-app-border text-app-text">
            {columns.map((column) => (
              <td key={column} className="px-3 py-3 align-top">
                {formatAnswer(row[column])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
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
    <div className="inline-flex items-center gap-3 rounded-[1.2rem] border border-app-border [background:var(--status-neutral-bg)] px-3 py-2">
      <button
        type="button"
        onClick={onPrev}
        disabled={page <= 0}
        className={cn(
          "inline-flex h-9 w-9 items-center justify-center rounded-xl border border-app-border [background:var(--control-bg)] text-app-text transition",
          page <= 0 ? "cursor-not-allowed opacity-40" : "hover:border-app-cyan/25 hover:text-app-cyan"
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
          "inline-flex h-9 w-9 items-center justify-center rounded-xl border border-app-border [background:var(--control-bg)] text-app-text transition",
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

function MetaMiniCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-app-border [background:var(--control-bg)] p-3">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">{label}</div>
      <div className="mt-2 text-sm text-app-text">{value}</div>
    </div>
  );
}

function SidebarRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-app-border [background:var(--status-neutral-bg)] p-3">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">{label}</div>
      <div className="mt-2 text-sm text-app-text">{value}</div>
    </div>
  );
}

function ContextSummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">{label}</div>
      <div className="mt-2 text-sm leading-6 text-app-text">{value}</div>
    </div>
  );
}

function StatusBanner({ tone, message }: { tone: StatusTone; message: string }) {
  return (
    <div
      className={cn(
        "rounded-[1.35rem] border px-5 py-4 text-sm leading-6",
        tone === "success" && "[border-color:var(--status-success-border)] [background:var(--status-success-bg)] [color:var(--status-success-text)]",
        tone === "warning" && "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
        tone === "error" && "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
        tone === "neutral" && "border-app-border [background:var(--status-neutral-bg)] text-app-muted"
      )}
    >
      {message}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-[1.2rem] border border-dashed border-app-border [background:var(--control-bg)] px-4 py-6 text-sm leading-6 text-app-muted">
      {message}
    </div>
  );
}

function formatMode(mode?: string | null) {
  if (mode === "split") return "Split Sample";
  if (mode === "mirror") return "Mirror Sample";
  if (mode === "stability") return "Stability Sample";
  return mode || "Unknown";
}

function formatQuestionType(questionType?: string | null) {
  if (!questionType) {
    return "Unknown";
  }
  return humanizeToken(questionType);
}

function buildRealismSummary(summary?: Record<string, unknown> | null) {
  if (!summary) {
    return "No realism summary is available.";
  }
  return `Realism score: ${String(summary.realism_score_0_to_100 ?? summary.realism_score ?? "n/a")} out of 100 across ${String(summary.questions_scored ?? 0)} questions. Distribution distance metrics: TV ${String(summary.weighted_tv_distance ?? "n/a")}, JS ${String(summary.weighted_js_divergence ?? "n/a")}.`;
}

function confidenceTone(label?: string | null): "cyan" | "gold" | "neutral" {
  if (label === "High confidence" || label === "Moderate confidence") {
    return "cyan";
  }
  if (label) {
    return "gold";
  }
  return "neutral";
}

function agreementTone(label?: string | null): "cyan" | "gold" | "neutral" {
  if (label === "Agreement") {
    return "cyan";
  }
  if (label) {
    return "gold";
  }
  return "neutral";
}

function buildAudienceAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Audience not configured yet.";
  }

  const geography = [value.state, value.metro, value.zip_code]
    .filter((entry) => typeof entry === "string" && entry.trim())
    .join(" • ");
  const ageMin = typeof value.age_min === "number" ? value.age_min : null;
  const ageMax = typeof value.age_max === "number" ? value.age_max : null;
  const ageRange =
    ageMin !== null || ageMax !== null
      ? `Ages ${ageMin ?? "any"}-${ageMax ?? "any"}`
      : "All ages";

  return [geography || "All geographies", ageRange].join(" • ");
}

function buildProductMarketAnchor(study: any) {
  const product = [
    toOptionalString(study?.product?.value?.product_name),
    toOptionalString(study?.product?.value?.product_type),
  ]
    .filter(Boolean)
    .join(" • ");
  const market = [
    toOptionalString(study?.market?.value?.category),
    Array.isArray(study?.market?.value?.direct_competitors)
      ? `${study.market.value.direct_competitors.length} competitors`
      : null,
  ]
    .filter(Boolean)
    .join(" • ");

  return [product || "No product", market || "No market context"].join(" | ");
}

function prettifyQuestionText(value: unknown) {
  const text = toOptionalString(value);
  if (!text) {
    return null;
  }
  return text.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/\s+/g, " ").trim();
}

function humanizeToken(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function toOptionalString(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function formatAnswer(answer: unknown) {
  if (Array.isArray(answer)) {
    return answer.map((entry) => String(entry)).join(" • ");
  }
  if (answer === null || typeof answer === "undefined" || answer === "") {
    return "n/a";
  }
  return String(answer);
}
