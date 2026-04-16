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

export function InsightsSection() {
  const { studyId, study } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [insights, setInsights] = useState<InsightsPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showDetailedInsights, setShowDetailedInsights] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function hydrateInsights() {
      if (!studyId) {
        if (!cancelled) {
          setInsights(null);
          setLoadError(null);
          setShowDetailedInsights(false);
          setIsLoading(false);
        }
        return;
      }

      if (!cancelled) {
        setIsLoading(true);
        setLoadError(null);
      }

      try {
        const result = await getInsights(studyId);
        if (cancelled) {
          return;
        }
        setInsights(result);
        setShowDetailedInsights(!result.llm_summary?.available);
      } catch (error) {
        if (!cancelled) {
          setInsights(null);
          setLoadError(
            error instanceof Error
              ? error.message
              : "Unable to load insights right now."
          );
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
  const llmSummary = insights?.llm_summary;
  const evidenceCount = insights?.evidence_package?.items?.length ?? 0;

  return (
    <SectionWrapper id="insights" scrollable contentClassName="relative scrollbar-hidden">
      <div className="grid items-start gap-8">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={9}
              eyebrow="Insights"
              title="LLM-Summarized Insights"
              description="These insights are summarized by the LLM from the synthetic survey responses and include a reliability confidence read, while the detailed view below shows the supporting signals, segments, and confidence context."
            />
          </RevealOnScroll>

          {isLoading ? (
            <GlassPanel className="p-6 sm:p-7">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-6">
                <div className="flex flex-wrap gap-3">
                  <BadgeChip tone="cyan">Loading Insights</BadgeChip>
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-app-muted">
                  Loading the latest run, evidence package, and executive summary.
                </p>
              </div>
            </GlassPanel>
          ) : !insights?.available ? (
            <GlassPanel className="p-6 sm:p-7">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-6">
                <div className="flex flex-wrap gap-3">
                  <BadgeChip tone="gold">Insights Unavailable</BadgeChip>
                  {insights?.run?.status ? <BadgeChip>{insights.run.status}</BadgeChip> : null}
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-app-muted">
                  {loadError ??
                    insights?.message ??
                    "No saved run is available yet. Complete Run Simulation first, then come here for executive summary and recommendations."}
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
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.7rem] border border-app-border [background:var(--theme-panel-gradient)] p-5 sm:p-6">
                    <div className="flex flex-wrap items-center gap-3">
                      <BadgeChip tone={llmSummary?.available ? "cyan" : "gold"}>
                        {llmSummary?.available ? "Research Summary" : "Summary Unavailable"}
                      </BadgeChip>
                      {llmSummary?.available ? (
                        <BadgeChip>{llmSummary.cached ? "Cached For This Run" : "Generated From Latest Run"}</BadgeChip>
                      ) : null}
                      {evidenceCount > 0 ? <BadgeChip>{`${evidenceCount} evidence points`}</BadgeChip> : null}
                      {llmSummary?.model ? <BadgeChip>{llmSummary.model}</BadgeChip> : null}
                    </div>

                    {llmSummary?.available ? (
                      <>
                        <div className="mt-5 rounded-[1.55rem] border border-app-cyan/20 bg-[linear-gradient(145deg,rgba(10,24,30,0.92),rgba(8,19,24,0.82))] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] md:p-7">
                          <div className="flex flex-wrap items-center gap-3">
                            <p className="text-[0.72rem] uppercase tracking-[0.24em] text-app-cyan/80">
                              Overview
                            </p>
                            {summary?.records_summary?.unique_respondents ? (
                              <BadgeChip>{`${summary.records_summary.unique_respondents} respondents`}</BadgeChip>
                            ) : null}
                            {summary?.records_summary?.questions ? (
                              <BadgeChip>{`${summary.records_summary.questions} questions`}</BadgeChip>
                            ) : null}
                          </div>
                          <p className="mt-5 text-[1.05rem] leading-9 text-app-text sm:text-[1.12rem] lg:text-[1.18rem] lg:leading-10">
                            {rewriteOverviewLead(llmSummary.overview)}
                          </p>
                          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.85fr)]">
                            <div className="rounded-[1.15rem] border border-white/8 bg-white/[0.03] px-4 py-3 text-sm leading-7 text-app-muted">
                              This summary is grounded in the same evidence package that powers the detailed insights below, so the headline and the deeper view stay aligned.
                            </div>
                            {llmSummary.researcher_note ? (
                              <div className="rounded-[1.2rem] border border-white/8 bg-white/[0.03] p-4 text-sm leading-7 text-app-muted">
                                <p className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
                                  Researcher Note
                                </p>
                                <p className="mt-2">{llmSummary.researcher_note}</p>
                              </div>
                            ) : null}
                          </div>
                        </div>

                        <div className="mt-5 grid gap-4 xl:grid-cols-3">
                          {(llmSummary.key_findings ?? []).length > 0 || llmSummary.result_reliability ? (
                            <>
                              {(llmSummary.key_findings ?? []).map((finding) => (
                                <ResearchFindingCard key={finding.title} finding={finding} />
                              ))}
                              {llmSummary.result_reliability ? (
                                <ReliabilityCard reliability={llmSummary.result_reliability} />
                              ) : null}
                            </>
                          ) : (
                            <div className="xl:col-span-3">
                              <EmptyState message="No research takeaways were returned for this summary yet." />
                            </div>
                          )}
                        </div>

                        <div className="mt-5">
                          <SummaryListCard
                            eyebrow="Recommended Next Steps"
                            tone="cyan"
                            items={
                              llmSummary.recommended_next_steps?.length
                                ? llmSummary.recommended_next_steps
                                : ["No explicit next steps were returned in the current summary."]
                            }
                          />
                        </div>
                      </>
                    ) : (
                      <div className="mt-5 rounded-[1.45rem] border [border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] p-5 text-sm leading-7 text-app-gold">
                        {llmSummary?.message ??
                          "The executive LLM summary is unavailable right now. Detailed insights are still available below."}
                      </div>
                    )}

                    <div className="mt-6 flex flex-wrap items-center gap-3">
                      <Button
                        variant={showDetailedInsights ? "secondary" : "primary"}
                        onClick={() => setShowDetailedInsights((value) => !value)}
                      >
                        {showDetailedInsights ? "Hide Detailed Insights" : "Show Detailed Insights"}
                      </Button>
                      <p className="text-sm leading-7 text-app-muted">
                        Detailed insights use the same evidence base as this summary.
                      </p>
                    </div>
                  </div>
                </GlassPanel>
              </RevealOnScroll>

              {showDetailedInsights ? (
                <>
                  <RevealOnScroll delay={0.1} amount={0.05}>
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="cyan">Detailed Insights</BadgeChip>
                        <BadgeChip>{`${displayedTopFindings.length} curated findings`}</BadgeChip>
                        {barrierRankingRows.length > 0 ? (
                          <BadgeChip>{`${barrierRankingRows.length} barrier items`}</BadgeChip>
                        ) : null}
                        {messagePerformanceRows.length > 0 ? (
                          <BadgeChip>{`${messagePerformanceRows.length} concept comparisons`}</BadgeChip>
                        ) : null}
                      </div>
                      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                        <HeroInsightCard
                          label="Top Use Case"
                          value={summary?.top_use_case?.label ?? "N/A"}
                          detail={
                            useCaseShareRows[0]?.valueLabel
                              ? `${useCaseShareRows[0].valueLabel} share in this run`
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
                          detail="Directional score from the latest run"
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
                              ? `${summary.model_difference.differing_questions} question(s) show meaningful spread`
                              : "No strong divergence called out"
                          }
                        />
                      </div>
                      <div className="space-y-4">
                        {displayedTopFindings.map((finding) => (
                          <TopFindingCard key={finding.id} finding={finding} />
                        ))}
                      </div>
                    </div>
                  </RevealOnScroll>

                  <RevealOnScroll delay={0.12} amount={0.08}>
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="gold">Segment and Positioning Story</BadgeChip>
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
                            Read the segment landscape at full width: where signals intensify, where they flatten, and which questions separate segments most.
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
                              detail="Segment with the strongest overall directional signal in this run."
                            />
                            <SegmentStorySpotlight
                              label="Weakest Segment"
                              value={insights.segment_story?.weakest_segment ?? "N/A"}
                              tone="gold"
                              detail="Segment with the weakest purchase-oriented pattern in this run."
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

                  <RevealOnScroll delay={0.14}>
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
                            Treat these outputs as directional guidance for next research moves, not validated market truth. Check important claims with real respondents.
                          </div>
                        </div>
                      </GlassPanel>

                      <GlassPanel className="p-5 sm:p-6">
                        <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                          <div className="flex flex-wrap gap-2">
                            <BadgeChip tone="gold">Trust Notes</BadgeChip>
                          </div>
                          <div className="mt-5 space-y-3">
                            <NarrativeNote>
                              {insights.context_notes?.run_warnings?.[0] ??
                                "No run notes were attached to the latest result."}
                            </NarrativeNote>
                            <NarrativeNote>
                              {insights.context_notes?.survey_parse_warnings?.[0] ??
                                "No survey parsing notes were attached to this run."}
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

                  <RevealOnScroll delay={0.16} amount={0.08}>
                    <GlassPanel className="p-5 sm:p-6">
                      <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                        <LadderChart
                          title="Interest Ladder"
                          subtitle="Movement from feasibility toward purchase likelihood."
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
              ) : null}
            </>
          )}
        </div>
      </div>
    </SectionWrapper>
  );
}

function ResearchFindingCard({
  finding,
}: {
  finding: {
    title: string;
    summary: string;
    why_it_matters: string;
    evidence_ids: string[];
  };
}) {
  return (
    <div className="rounded-[1.35rem] border border-app-border bg-[linear-gradient(180deg,rgba(118,228,255,0.08),rgba(255,255,255,0.03))] p-5">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeChip tone="cyan">{finding.title}</BadgeChip>
        <BadgeChip>{`${finding.evidence_ids.length} evidence source${finding.evidence_ids.length === 1 ? "" : "s"}`}</BadgeChip>
      </div>
      <p className="mt-4 text-base leading-7 text-app-text">{finding.summary}</p>
      <p className="mt-3 text-sm leading-7 text-app-muted">{finding.why_it_matters}</p>
    </div>
  );
}

function ReliabilityCard({
  reliability,
}: {
  reliability: {
    level: string;
    summary: string;
    reason: string;
    evidence_ids: string[];
  };
}) {
  return (
    <div className="rounded-[1.35rem] border border-app-gold/20 bg-[linear-gradient(180deg,rgba(216,186,103,0.1),rgba(255,255,255,0.03))] p-5">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeChip tone="gold">Result Reliability</BadgeChip>
        <BadgeChip>{reliability.level}</BadgeChip>
        <BadgeChip>{`${reliability.evidence_ids.length} evidence source${reliability.evidence_ids.length === 1 ? "" : "s"}`}</BadgeChip>
      </div>
      <p className="mt-4 text-base leading-7 text-app-text">{reliability.summary}</p>
      <div className="mt-4 rounded-[1.1rem] border border-white/8 bg-white/[0.03] p-4">
        <p className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">Why This Confidence Level</p>
        <p className="mt-2 text-sm leading-7 text-app-muted">{reliability.reason}</p>
      </div>
    </div>
  );
}

function SummaryListCard({
  eyebrow,
  items,
  tone,
}: {
  eyebrow: string;
  items: string[];
  tone: "cyan" | "gold";
}) {
  return (
    <div
      className={cn(
        "self-start rounded-[1.35rem] border p-5",
        tone === "cyan"
          ? "border-app-cyan/20 bg-[linear-gradient(180deg,rgba(15,216,255,0.08),rgba(255,255,255,0.03))]"
          : "border-app-gold/20 bg-[linear-gradient(180deg,rgba(216,186,103,0.08),rgba(255,255,255,0.03))]"
      )}
    >
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">{eyebrow}</div>
        <BadgeChip tone={tone}>{`${items.length} item${items.length === 1 ? "" : "s"}`}</BadgeChip>
      </div>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-app-muted">
        {tone === "gold"
          ? "These are the main reasons to stay cautious when reading the current result."
          : "These are the clearest follow-up actions suggested by the current evidence base, organized as the most practical next moves."}
      </p>
      <div className="mt-4 space-y-3">
        {items.map((item, index) => (
          <div
            key={`${eyebrow}-${index}`}
            className="rounded-[1.15rem] border border-white/8 bg-[rgba(255,255,255,0.03)] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
          >
            <div className="flex items-start gap-4">
              <div
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-xs font-semibold tracking-[0.14em]",
                  tone === "cyan"
                    ? "border-app-cyan/35 bg-app-cyan/10 text-app-cyan"
                    : "border-app-gold/35 bg-app-gold/10 text-app-gold"
                )}
              >
                {String(index + 1).padStart(2, "0")}
              </div>
              <div className="min-w-0">
                <p className="text-sm leading-7 text-app-text">{item}</p>
                <p className="mt-2 text-sm leading-7 text-app-muted">
                  {buildSummarySupportText({ item, tone })}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function buildSummarySupportText({
  item,
  tone,
}: {
  item: string;
  tone: "cyan" | "gold";
}) {
  const normalized = item.toLowerCase();

  if (tone === "gold") {
    if (
      normalized.includes("small respondent") ||
      normalized.includes("small sample") ||
      normalized.includes("respondent count") ||
      normalized.includes("generalizability")
    ) {
      return "What this means: the signal is useful for direction, but the base is still too narrow to treat as broadly representative.";
    }
    if (normalized.includes("needs validation") || normalized.includes("confidence")) {
      return "What this means: keep the insight as a working hypothesis and confirm it with additional runs or real respondent research before relying on it heavily.";
    }
    if (normalized.includes("model") || normalized.includes("agreement")) {
      return "What this means: check whether the same pattern holds across repeated runs or across the models you selected before turning it into a firm conclusion.";
    }
    return "What this means: use this as a caution flag when interpreting the current run, especially for any decision with real product or positioning consequences.";
  }

  if (
    normalized.includes("test") ||
    normalized.includes("validate") ||
    normalized.includes("confirm")
  ) {
    return "Why this matters: it tightens confidence around the strongest pattern before you commit to a bigger product, pricing, or messaging decision.";
  }
  if (normalized.includes("segment") || normalized.includes("persona")) {
    return "Why this matters: segment-specific follow-up is usually the fastest way to understand whether one strong signal is broad or concentrated in a narrower audience slice.";
  }
  if (normalized.includes("message") || normalized.includes("concept") || normalized.includes("position")) {
    return "Why this matters: clearer message testing helps translate the signal into a usable go-to-market direction instead of leaving it as a generic insight.";
  }
  return "Why this matters: it turns the current evidence into a concrete next move instead of stopping at a directional readout.";
}

function rewriteOverviewLead(text?: string) {
  const value = (text || "").trim();
  if (!value) {
    return "Executive summary unavailable for this run.";
  }

  const surveyLeadPattern =
    /^The\s+.+?\s+Survey\s+reveals\s+/i;
  if (surveyLeadPattern.test(value)) {
    return value.replace(surveyLeadPattern, "The result reveals ");
  }

  return value;
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
        subtitle="Read exact appeal and purchase values alongside the pattern."
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
      subtitle="Read ranking and exact values together."
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

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-[1.15rem] border border-dashed border-app-border [background:var(--control-bg)] px-4 py-5 text-sm leading-7 text-app-muted">
      {message}
    </div>
  );
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
