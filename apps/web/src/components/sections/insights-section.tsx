"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { GroupedBarChart } from "@/components/charts/grouped-bar-chart";
import { HeatmapGrid } from "@/components/charts/heatmap-grid";
import { HorizontalBarChart } from "@/components/charts/horizontal-bar-chart";
import { LadderChart } from "@/components/charts/ladder-chart";
import { ModelDifferenceChart as InsightsModelDifferenceChart } from "@/components/charts/model-difference-chart";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import { InsightsPayload, InsightsTopFinding, getInsights } from "@/lib/api";
import {
  toBarrierRankingRows,
  toFindingChartModel,
  toHeatmapModel,
  toInterestLadderSteps,
  toMessagePerformanceRows,
  toModelDifferenceModel,
  toUseCaseShareRows,
} from "@/lib/insights-chart-adapters";
import { cn } from "@/lib/utils";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { useStudy } from "@/providers/study-provider";

type StatusTone = "neutral" | "success" | "warning" | "error";

type StatusState = {
  tone: StatusTone;
  message: string;
};

const EMPTY_STATUS: StatusState = {
  tone: "neutral",
  message:
    "Insights will load from the latest saved run once a simulation result is available.",
};

export function InsightsSection() {
  const { studyId, study } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [insights, setInsights] = useState<InsightsPayload | null>(null);
  const [status, setStatus] = useState<StatusState>(EMPTY_STATUS);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function hydrateInsights() {
      if (!studyId) {
        if (!cancelled) {
          setInsights(null);
          setStatus(EMPTY_STATUS);
        }
        return;
      }

      setIsLoading(true);
      try {
        const result = await getInsights(studyId);
        if (cancelled) {
          return;
        }
        setInsights(result);
        setStatus(
          result.available
            ? {
                tone: "success",
                message:
                  "Executive insights are loaded from the latest saved run. Treat them as exploratory decision support, not final proof.",
              }
            : {
                tone: "warning",
                message:
                  result.message ??
                  "No saved insights payload is available yet. Complete Run Simulation first.",
              }
        );
      } catch (error) {
        if (!cancelled) {
          setStatus({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Unable to load insights right now.",
          });
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void hydrateInsights();

    return () => {
      cancelled = true;
    };
  }, [studyId, study?.updated_at]);

  const summary = insights?.executive_summary;
  const trustSnapshot = insights?.trust_snapshot;
  const charts = insights?.charts;
  const barrierRankingRows = useMemo(
    () => (insights ? toBarrierRankingRows(insights) : []),
    [insights]
  );
  const useCaseShareRows = useMemo(
    () => (insights ? toUseCaseShareRows(insights) : []),
    [insights]
  );
  const messagePerformanceRows = useMemo(
    () => (insights ? toMessagePerformanceRows(insights) : []),
    [insights]
  );
  const heatmapModel = useMemo(
    () => (insights ? toHeatmapModel(insights) : null),
    [insights]
  );
  const interestSteps = useMemo(
    () => (insights ? toInterestLadderSteps(insights) : []),
    [insights]
  );
  const modelDifferenceModel = useMemo(
    () => (insights ? toModelDifferenceModel(insights) : null),
    [insights]
  );
  const displayedTopFindings = useMemo(
    () => (insights?.top_findings ?? []).filter((finding) => finding.chart_kind !== "ladder"),
    [insights]
  );

  const contextSummary = useMemo(
    () => ({
      audience: buildAudienceAnchor(study?.audience?.value),
      product: buildProductAnchor(study?.product?.value),
      market: buildMarketAnchor(study?.market?.value),
      survey:
        study?.survey?.source_filename && study?.survey?.question_count
          ? `${study.survey.source_filename} • ${study.survey.question_count} questions`
          : "Survey not configured yet.",
    }),
    [study]
  );

  return (
    <SectionWrapper id="insights" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1.03fr)_24rem] 2xl:grid-cols-[minmax(0,1.04fr)_28rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={9}
              eyebrow="Insights"
              title="Turn the run into the clearest executive takeaways."
              description="This chapter is the decision layer above Analysis: the biggest signals first, the segment and positioning story second, and clear trust framing throughout."
            />
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <div className="rounded-[1.45rem] border [border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] px-5 py-4 text-sm leading-6 text-app-gold">
              {insights?.transparency_note ??
                "Transparency note: findings, confidence labels, and agreement labels are deterministic rule-based summaries."}
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={0.06}>
            <StatusBanner tone={status.tone} message={status.message} />
          </RevealOnScroll>

          {!insights?.available ? (
            <GlassPanel className="p-6 sm:p-7">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-6">
                <div className="flex flex-wrap gap-3">
                  <BadgeChip tone="gold">Insights Unavailable</BadgeChip>
                  {insights?.run?.status ? <BadgeChip>{insights.run.status}</BadgeChip> : null}
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-app-muted">
                  {insights?.message ??
                    "No saved run is available yet. Complete Run Simulation first, then come here for the executive summary and recommendation layer."}
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
                    Context & Workflow
                  </summary>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <ContextSummaryCard
                      label="Run"
                      value={
                        [
                          insights.run?.run_id,
                          insights.run?.survey_title,
                          insights.run?.experiment_mode
                            ? formatMode(insights.run.experiment_mode)
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" • ") || "No saved run"
                      }
                    />
                    <ContextSummaryCard
                      label="Workflow"
                      value={
                        study?.derived?.workflow?.ready_for_persona_preview
                          ? "Setup stack was fully saved before run."
                          : "The run should still be interpreted as exploratory."
                      }
                    />
                    <ContextSummaryCard label="Audience" value={contextSummary.audience} />
                    <ContextSummaryCard
                      label="Product / Market / Survey"
                      value={`${contextSummary.product} • ${contextSummary.market} • ${contextSummary.survey}`}
                    />
                  </div>
                </details>
              </RevealOnScroll>

              <RevealOnScroll delay={0.1}>
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.7rem] border border-app-border [background:var(--theme-panel-gradient)] p-5 sm:p-6">
                    <div className="flex flex-wrap items-center gap-3">
                      <BadgeChip tone="cyan">Executive Summary</BadgeChip>
                      {insights.run?.run_id ? <BadgeChip>{insights.run.run_id}</BadgeChip> : null}
                      {isLoading ? <BadgeChip>Refreshing</BadgeChip> : null}
                    </div>

                    <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                      <HeroInsightCard
                        label="Top Use Case"
                        value={summary?.top_use_case?.label ?? "N/A"}
                        detail={
                          useCaseShareRows[0]?.valueLabel
                            ? `${useCaseShareRows[0].valueLabel} share`
                            : "Use-case signal unavailable"
                        }
                      />
                      <HeroInsightCard
                        label="Average Interest"
                        value={
                          summary?.average_interest !== null &&
                          summary?.average_interest !== undefined
                            ? String(summary.average_interest)
                            : "N/A"
                        }
                        detail="Directional signal from the run"
                      />
                      <HeroInsightCard
                        label="Strongest Segment"
                        value={summary?.strongest_segment ?? "N/A"}
                        detail="Based on current interest-oriented questions"
                      />
                      <HeroInsightCard
                        label="Model Difference"
                        value={summary?.model_difference?.status ?? "N/A"}
                        detail={
                          summary?.model_difference?.differing_questions
                            ? `${summary.model_difference.differing_questions} question(s) differ`
                            : "No strong divergence called out"
                        }
                      />
                    </div>

                    <div className="mt-5 flex flex-wrap gap-3 text-sm text-app-muted">
                      <span>{`${summary?.records_summary?.total_records ?? 0} records`}</span>
                      <span className="text-white/20">•</span>
                      <span>{`${summary?.records_summary?.unique_respondents ?? 0} respondents`}</span>
                      <span className="text-white/20">•</span>
                      <span>{`${summary?.records_summary?.questions ?? 0} questions`}</span>
                      <span className="text-white/20">•</span>
                      <span>{summary?.records_summary?.survey_title ?? "Untitled survey"}</span>
                    </div>
                  </div>
                </GlassPanel>
              </RevealOnScroll>

              <RevealOnScroll delay={0.12} amount={0.05}>
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <BadgeChip tone="cyan">Key Takeaways With Visual Proof</BadgeChip>
                    <BadgeChip>{`${displayedTopFindings.length} curated findings`}</BadgeChip>
                    {barrierRankingRows.length > 0 ? (
                      <BadgeChip>{`${barrierRankingRows.length} barrier items`}</BadgeChip>
                    ) : null}
                    {messagePerformanceRows.length > 0 ? (
                      <BadgeChip>{`${messagePerformanceRows.length} concept comparisons`}</BadgeChip>
                    ) : null}
                  </div>
                  <div className="space-y-4">
                    {displayedTopFindings.map((finding) => (
                      <TopFindingCard key={finding.id} finding={finding} />
                    ))}
                  </div>
                </div>
              </RevealOnScroll>

              <RevealOnScroll delay={0.14} amount={0.08}>
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <BadgeChip tone="gold">Segment & Positioning Story</BadgeChip>
                  </div>

                  <GlassPanel className="p-5 sm:p-6">
                    <div className="rounded-[1.65rem] border border-app-border [background:var(--theme-panel-gradient)] p-5 sm:p-6">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="cyan">Segment Difference Heatmap</BadgeChip>
                        {charts?.segment_heatmap?.available ? (
                          <BadgeChip>{`${charts.segment_heatmap.segments?.length ?? 0} segments`}</BadgeChip>
                        ) : null}
                      </div>
                      <p className="mt-4 max-w-3xl text-sm leading-7 text-app-muted">
                        Read the segment landscape at full width: where signals intensify, where they flatten, and which questions separate segments the most.
                      </p>
                      <div className="mt-6">
                        <HeatmapGrid
                          title="Segment Difference Heatmap"
                          subtitle="Key numeric questions by segment, with exact values kept visible."
                          columns={heatmapModel?.columns ?? []}
                          rows={heatmapModel?.rows ?? []}
                          badges={
                            charts?.segment_heatmap?.available
                              ? [
                                  {
                                    label: `${heatmapModel?.columns.length ?? 0} segments`,
                                  },
                                ]
                              : undefined
                          }
                          emptyMessage={
                            charts?.segment_heatmap?.message ??
                            "No segment heatmap is available yet."
                          }
                          note="Cell color is directional emphasis only; the numbers inside each cell remain the source of truth."
                        />
                      </div>
                    </div>
                  </GlassPanel>

                  <GlassPanel className="p-5 sm:p-6">
                    <div className="rounded-[1.65rem] border border-app-border [background:var(--theme-panel-gradient)] p-5 sm:p-6">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="gold">Segment Story</BadgeChip>
                        {(insights.segment_story?.notes ?? []).length > 0 ? (
                          <BadgeChip>{`${insights.segment_story?.notes?.length ?? 0} narrative notes`}</BadgeChip>
                        ) : null}
                      </div>
                      <div className="mt-6 grid gap-4 xl:grid-cols-3">
                        <SegmentStorySpotlight
                          label="Strongest Segment"
                          value={insights.segment_story?.strongest_segment ?? "N/A"}
                          tone="cyan"
                          detail="The segment with the strongest overall directional signal in this run."
                        />
                        <SegmentStorySpotlight
                          label="Weakest Segment"
                          value={insights.segment_story?.weakest_segment ?? "N/A"}
                          tone="gold"
                          detail="The segment showing the weakest purchase-oriented pattern."
                        />
                        <SegmentStorySpotlight
                          label="Story Shape"
                          value={
                            (insights.segment_story?.notes ?? []).length > 0
                              ? "Differences observed"
                              : "Limited divergence"
                          }
                          tone="neutral"
                          detail="Use the notes below to understand whether differences are sharp, narrow, or mostly directional."
                        />
                      </div>
                      <div className="mt-6 grid gap-4 lg:grid-cols-2">
                        {(insights.segment_story?.notes ?? []).length > 0 ? (
                          (insights.segment_story?.notes ?? []).map((note) => (
                            <NarrativeNote key={note}>{note}</NarrativeNote>
                          ))
                        ) : (
                          <div className="lg:col-span-2">
                            <EmptyState message="No strong segment notes were generated from the latest run." />
                          </div>
                        )}
                      </div>
                    </div>
                  </GlassPanel>

                  <GlassPanel className="p-5 sm:p-6">
                    <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="gold">Model Difference</BadgeChip>
                        {modelDifferenceModel ? (
                          <BadgeChip>{`${modelDifferenceModel.rows.length} question spreads`}</BadgeChip>
                        ) : null}
                      </div>
                      <div className="mt-5">
                        <InsightsModelDifferenceChart
                          title="Model Difference"
                          subtitle="Only rendered when multiple models were used in the run."
                          rows={modelDifferenceModel?.rows ?? []}
                          models={modelDifferenceModel?.models ?? []}
                          emptyMessage={
                            charts?.model_difference?.message ??
                            "Not enough multi-model coverage to compare model differences."
                          }
                          note="This is a compact directional comparison, not a formal model benchmark."
                        />
                      </div>
                    </div>
                  </GlassPanel>
                </div>
              </RevealOnScroll>

              <RevealOnScroll delay={0.16}>
                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.82fr)]">
                  <GlassPanel className="p-5 sm:p-6">
                    <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                      <div className="flex flex-wrap gap-2">
                        <BadgeChip tone="cyan">Recommendations</BadgeChip>
                        <BadgeChip tone="gold">Exploratory only</BadgeChip>
                      </div>
                      <div className="mt-5 space-y-3">
                        {(insights.recommendations ?? []).map((recommendation, index) => (
                          <RecommendationRow
                            key={recommendation}
                            index={index + 1}
                            body={recommendation}
                          />
                        ))}
                      </div>
                      <div className="mt-5 rounded-[1.25rem] border [border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] p-4 text-sm leading-7 text-app-gold">
                        Treat these outputs as decision support for the next research move, not as validated market truth. Important claims should be checked with real respondents.
                      </div>
                    </div>
                  </GlassPanel>

                  <GlassPanel className="p-5 sm:p-6">
                    <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                      <div className="flex flex-wrap gap-2">
                        <BadgeChip tone="gold">Trust Framing</BadgeChip>
                      </div>
                      <div className="mt-5 space-y-3">
                        <NarrativeNote>
                          {insights.context_notes?.run_warnings?.[0] ??
                            "Run warnings were not attached to the latest result."}
                        </NarrativeNote>
                        <NarrativeNote>
                          {insights.context_notes?.survey_parse_warnings?.[0] ??
                            "Survey parser notes are not currently changing the executive summary, but should still be reviewed."}
                        </NarrativeNote>
                        <NarrativeNote>
                          {summary?.model_difference?.note ??
                            "Model comparison notes are unavailable for this run."}
                        </NarrativeNote>
                      </div>
                    </div>
                  </GlassPanel>
                </div>
              </RevealOnScroll>

              <RevealOnScroll delay={0.18} amount={0.08}>
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                    <LadderChart
                      title="Interest Ladder"
                      subtitle="Movement from feasibility into purchase likelihood."
                      steps={interestSteps}
                      badges={
                        interestSteps.length > 0
                          ? [{ label: `${interestSteps.length} steps`, tone: "cyan" }]
                          : undefined
                      }
                      emptyMessage={
                        charts?.interest_ladder?.message ??
                        "No decision ladder is available yet."
                      }
                      note="This is a clean progression view, not a statistical funnel."
                    />
                  </div>
                </GlassPanel>
              </RevealOnScroll>
            </>
          )}
        </div>

        <RevealOnScroll
          delay={0.08}
          className="min-w-0 lg:sticky lg:top-6 lg:w-full lg:max-w-[22rem] lg:justify-self-end xl:max-w-[24rem] 2xl:max-w-[28rem]"
        >
          <div className="space-y-5">
            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="cyan">Run Snapshot</BadgeChip>
                  {isLoading ? <BadgeChip>Refreshing</BadgeChip> : null}
                </div>
                <div className="mt-5 space-y-3">
                  <SidebarRow label="Run ID" value={insights?.run?.run_id ?? "No saved run"} />
                  <SidebarRow label="Survey" value={insights?.run?.survey_title ?? "Unavailable"} />
                  <SidebarRow
                    label="Generated"
                    value={
                      insights?.run?.generated_responses !== undefined
                        ? `${insights.run.generated_responses} responses`
                        : "Unavailable"
                    }
                  />
                  <SidebarRow
                    label="Models"
                    value={
                      insights?.run?.models_used?.length
                        ? insights.run.models_used.join(", ")
                        : "Unavailable"
                    }
                  />
                </div>
              </div>
            </GlassPanel>

            <GlassPanel className="p-5 sm:p-6">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                <div className="flex flex-wrap gap-2">
                  <BadgeChip tone="gold">Trust Snapshot</BadgeChip>
                </div>
                <div className="mt-5 grid gap-3">
                  <TrustMiniCard
                    label="Confidence"
                    value={trustSnapshot?.confidence_summary?.dominant_label ?? "Needs validation"}
                    detail={buildCountsSummary(trustSnapshot?.confidence_summary?.counts)}
                  />
                  <TrustMiniCard
                    label="Agreement"
                    value={trustSnapshot?.agreement_summary?.dominant_label ?? "Partial agreement"}
                    detail={buildCountsSummary(trustSnapshot?.agreement_summary?.counts)}
                  />
                  <TrustMiniCard
                    label="Realism"
                    value={trustSnapshot?.realism_snapshot?.label ?? "Unavailable"}
                    detail={trustSnapshot?.realism_snapshot?.detail ?? "No realism detail available."}
                  />
                  <TrustMiniCard
                    label="Benchmark"
                    value={trustSnapshot?.benchmark_snapshot?.label ?? "Unavailable"}
                    detail={trustSnapshot?.benchmark_snapshot?.detail ?? "No benchmark detail available."}
                  />
                </div>
              </div>
            </GlassPanel>
          </div>
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}

function TopFindingCard({ finding }: { finding: InsightsTopFinding }) {
  const chartModel = useMemo(() => toFindingChartModel(finding), [finding]);

  return (
    <GlassPanel className="p-5 sm:p-6">
      <div className="rounded-[1.65rem] border border-app-border [background:var(--theme-panel-gradient)] p-5 sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <BadgeChip tone="cyan">{finding.title}</BadgeChip>
          {finding.confidence_label ? <BadgeChip>{finding.confidence_label}</BadgeChip> : null}
          {finding.agreement_label ? <BadgeChip tone="gold">{finding.agreement_label}</BadgeChip> : null}
        </div>
        <h3 className="mt-4 text-lg font-medium leading-8 text-app-text">{finding.headline}</h3>
        <p className="mt-3 text-sm leading-7 text-app-muted">{finding.summary}</p>
        <div className="mt-5">
          <FindingChart finding={finding} chartModel={chartModel} />
        </div>
      </div>
    </GlassPanel>
  );
}

function FindingChart({
  finding,
  chartModel,
}: {
  finding: InsightsTopFinding;
  chartModel: ReturnType<typeof toFindingChartModel>;
}) {
  if (!chartModel) {
    return <EmptyState message="No visual proof is available for this takeaway yet." />;
  }

  if (chartModel.kind === "grouped") {
    return (
      <GroupedBarChart
        title={finding.title}
        subtitle="Exact appeal and purchase values remain visible."
        rows={chartModel.rows}
        headerless
        emptyMessage="No message-performance comparison is available yet."
      />
    );
  }

  if (chartModel.kind === "ladder") {
    return (
      <LadderChart
        title={finding.title}
        subtitle="This shows where momentum holds or fades across the decision path."
        steps={chartModel.steps}
        headerless
        emptyMessage="No decision ladder is available yet."
      />
    );
  }

  return (
    <HorizontalBarChart
      title={finding.title}
      subtitle="Read the ranking and the exact values together."
      rows={chartModel.rows}
      headerless
      emptyMessage="No visual proof is available for this takeaway yet."
      highlightTopRow
    />
  );
}

function HeroInsightCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-[1.25rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">{label}</div>
      <div className="mt-3 text-xl font-medium leading-8 text-app-text">{value}</div>
      <div className="mt-2 text-sm leading-6 text-app-muted">{detail}</div>
    </div>
  );
}

function TrustMiniCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-[1.15rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">{label}</div>
      <div className="mt-2 text-base font-medium text-app-text">{value}</div>
      <div className="mt-2 text-sm leading-6 text-app-muted">{detail}</div>
    </div>
  );
}

function NarrativeNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[1.25rem] border border-app-border [background:var(--theme-panel-inline-gradient)] p-5 text-sm leading-7 text-app-text shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      {children}
    </div>
  );
}

function SegmentStorySpotlight({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: "cyan" | "gold" | "neutral";
}) {
  return (
    <div
      className={cn(
        "rounded-[1.35rem] border p-5",
        tone === "cyan" &&
          "border-app-cyan/20 bg-[linear-gradient(180deg,rgba(15,216,255,0.1),rgba(255,255,255,0.02))]",
        tone === "gold" &&
          "border-app-gold/20 bg-[linear-gradient(180deg,rgba(216,186,103,0.1),rgba(255,255,255,0.02))]",
        tone === "neutral" && "border-app-border [background:var(--status-neutral-bg)]"
      )}
    >
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">{label}</div>
      <div className="mt-3 text-2xl font-medium leading-9 text-app-text">{value}</div>
      <div className="mt-3 text-sm leading-7 text-app-muted">{detail}</div>
    </div>
  );
}

function RecommendationRow({ index, body }: { index: number; body: string }) {
  return (
    <div className="flex gap-3 rounded-[1.1rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-app-cyan/30 bg-app-cyan/10 text-sm font-medium text-app-cyan">
        {index}
      </div>
      <div className="text-sm leading-7 text-app-text">{body}</div>
    </div>
  );
}

function ContextSummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.2rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
      <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">{label}</div>
      <div className="mt-2 text-sm leading-7 text-app-text">{value}</div>
    </div>
  );
}

function SidebarRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.05rem] border border-app-border [background:var(--status-neutral-bg)] p-3">
      <div className="text-[0.68rem] uppercase tracking-[0.2em] text-app-muted">{label}</div>
      <div className="mt-2 text-sm leading-6 text-app-text">{value}</div>
    </div>
  );
}

function StatusBanner({ tone, message }: { tone: StatusTone; message: string }) {
  return (
    <div
      className={cn(
        "rounded-[1.35rem] border px-5 py-4 text-sm leading-6",
        tone === "success" && "border-app-cyan/25 bg-[rgba(15,216,255,0.08)] text-app-cyan",
        tone === "warning" && "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
        tone === "error" && "border-rose-400/25 bg-[rgba(251,113,133,0.08)] text-rose-200",
        tone === "neutral" && "border-app-border [background:var(--status-neutral-bg)] text-app-muted"
      )}
    >
      {message}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-[1.15rem] border border-dashed border-app-border [background:var(--control-bg)] px-4 py-5 text-sm leading-7 text-app-muted">
      {message}
    </div>
  );
}

function buildCountsSummary(counts?: Record<string, number>) {
  if (!counts || Object.keys(counts).length === 0) {
    return "No summary available.";
  }
  return Object.entries(counts)
    .map(([label, count]) => `${label}: ${count}`)
    .join(" • ");
}

function buildAudienceAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Audience not configured yet.";
  }
  const geography = value.state || value.metro || value.zip_code || "All geographies";
  const ages =
    value.age_min || value.age_max
      ? `Ages ${value.age_min ?? "any"}-${value.age_max ?? "any"}`
      : "All ages";
  return `${geography} • ${ages}`;
}

function buildProductAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Product not configured yet.";
  }
  return [
    value.product_name,
    value.product_type,
    value.price_range,
  ]
    .filter(Boolean)
    .join(" • ") || "Product configured";
}

function buildMarketAnchor(value?: Record<string, unknown> | null) {
  if (!value) {
    return "Market not configured yet.";
  }
  return [
    value.category,
    Array.isArray(value.direct_competitors)
      ? `${value.direct_competitors.length} competitors`
      : null,
    Array.isArray(value.substitutes) ? `${value.substitutes.length} substitutes` : null,
  ]
    .filter(Boolean)
    .join(" • ") || "Market configured";
}

function formatMode(mode: string) {
  return mode
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
