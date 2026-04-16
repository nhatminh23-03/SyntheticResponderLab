"use client";

import { useEffect, useRef, useState } from "react";

import {
  AnalysisDashboardDistributionRow,
  AnalysisDashboardHistogramBin,
  AnalysisDashboardLinePoint,
  AnalysisDashboardQuestion,
  AnalysisDashboardQuote,
  AnalysisDashboardWordCloudTerm,
  AnalysisPayload,
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
import { StabilityCheckPanel } from "@/components/sections/stability-check-panel";
import { ChartFrame } from "@/components/charts/chart-frame";

const EMPTY_MESSAGE = "Analysis loads after a run is completed and saved.";
const OPEN_TEXT_LIMIT = 5;
const WORD_CLOUD_SLOTS = [
  { x: 50, y: 48, rotate: -2 },
  { x: 34, y: 60, rotate: 0 },
  { x: 64, y: 58, rotate: 1 },
  { x: 50, y: 26, rotate: -1 },
  { x: 28, y: 38, rotate: -3 },
  { x: 71, y: 36, rotate: 2 },
  { x: 40, y: 76, rotate: 1 },
  { x: 61, y: 74, rotate: -2 },
  { x: 19, y: 52, rotate: 1 },
  { x: 80, y: 51, rotate: -1 },
  { x: 24, y: 26, rotate: -2 },
  { x: 76, y: 24, rotate: 2 },
  { x: 15, y: 71, rotate: 0 },
  { x: 86, y: 68, rotate: -3 },
  { x: 40, y: 18, rotate: 1 },
  { x: 61, y: 18, rotate: -1 },
  { x: 32, y: 87, rotate: -2 },
  { x: 69, y: 87, rotate: 1 },
] as const;

export function AnalysisSection() {
  const { studyId, study } = useStudy();
  const { scrollToSection } = useSectionRegistry();
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState("All");
  const [isStabilityOpen, setIsStabilityOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function hydrateAnalysisDashboard() {
      if (!studyId) {
        if (!cancelled) {
          setAnalysis(null);
        }
        return;
      }

      setIsLoading(true);
      try {
        const result = await getAnalysis(studyId, {
          model: selectedModel,
          openTextLimit: OPEN_TEXT_LIMIT,
        });

        if (!cancelled) {
          setAnalysis(result);
        }
      } catch (error) {
        if (!cancelled) {
          setAnalysis({
            available: false,
            message:
              error instanceof Error ? error.message : "Unable to load analysis right now.",
          });
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void hydrateAnalysisDashboard();

    return () => {
      cancelled = true;
    };
  }, [studyId, study?.updated_at, selectedModel]);

  const dashboard = analysis?.dashboard;
  const modelOptions = dashboard?.model_options ?? ["All"];
  const questions = dashboard?.questions ?? [];

  return (
    <SectionWrapper
      id="analysis"
      scrollable
      contentClassName="relative scrollbar-hidden"
    >
      <div className="grid items-start gap-8">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={8}
              eyebrow="Analysis"
              title="Read every survey question as a response dashboard."
              description="Review the latest run question by question, switch the model view when needed, then optionally check repeatability at the bottom."
            />
          </RevealOnScroll>

          {!analysis?.available ? (
            <GlassPanel className="p-6 sm:p-7">
              <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-6">
                <div className="flex flex-wrap items-center gap-3">
                  <BadgeChip tone="gold">Analysis Unavailable</BadgeChip>
                  {isLoading ? <BadgeChip>Loading</BadgeChip> : null}
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-app-muted">
                  {analysis?.message ?? EMPTY_MESSAGE}
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
              <div className="sticky top-0 z-20 -mx-1 bg-[linear-gradient(180deg,rgba(7,11,15,0.96)_0%,rgba(7,11,15,0.88)_78%,rgba(7,11,15,0)_100%)] px-1 pb-5 pt-1">
                <div className="rounded-[1.55rem] border border-app-border/70 px-5 py-4 shadow-[0_18px_44px_rgba(0,0,0,0.24)] backdrop-blur-xl [background:linear-gradient(180deg,rgba(16,23,29,0.92),rgba(13,19,24,0.88))] sm:px-6">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex flex-wrap items-center gap-3">
                      <h2 className="text-[1.55rem] font-semibold tracking-tight text-app-text sm:text-[1.75rem]">
                        Result Dashboard
                      </h2>
                      <span className="inline-flex items-center rounded-full border border-app-border/70 px-3.5 py-1.5 text-sm font-medium text-app-muted [background:var(--status-neutral-bg)]">
                        {`${questions.length} questions`}
                      </span>
                      {isLoading ? <BadgeChip>Refreshing</BadgeChip> : null}
                    </div>

                    <div className="w-full max-w-md lg:w-[23rem]">
                      <div className="mb-2 text-[0.72rem] uppercase tracking-[0.22em] text-app-muted">
                        Filter Results By Model
                      </div>
                      <SelectInput
                        value={selectedModel}
                        onChange={setSelectedModel}
                        options={modelOptions.map((model) => ({
                          label: model === "All" ? "Overall Results" : model,
                          value: model,
                        }))}
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid gap-5 xl:grid-cols-2">
                {questions.length > 0 ? (
                  questions.map((question) => (
                    <QuestionDashboardCard
                      key={question.question_id}
                      question={question}
                    />
                  ))
                ) : (
                  <GlassPanel className="p-5 sm:p-6 xl:col-span-2">
                    <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-6 text-sm leading-7 text-app-muted">
                      No question-level analysis is available for this run yet.
                    </div>
                  </GlassPanel>
                )}
              </div>

              <RevealOnScroll delay={0.08}>
                <GlassPanel className="p-5 sm:p-6">
                  <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex flex-wrap items-center gap-3">
                        <BadgeChip tone="gold">Stability Check</BadgeChip>
                        <BadgeChip>Optional</BadgeChip>
                      </div>
                      <Button
                        variant="secondary"
                        onClick={() => setIsStabilityOpen((current) => !current)}
                      >
                        {isStabilityOpen ? "Hide Stability Check" : "Show Stability Check"}
                      </Button>
                    </div>

                    {isStabilityOpen ? (
                      <div className="mt-5">
                        <StabilityCheckPanel studyId={studyId} />
                      </div>
                    ) : null}
                  </div>
                </GlassPanel>
              </RevealOnScroll>
            </>
          )}
        </div>
      </div>
    </SectionWrapper>
  );
}

function QuestionDashboardCard({
  question,
}: {
  question: AnalysisDashboardQuestion;
}) {
  const [isVisible, setIsVisible] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || isVisible) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "240px 0px" }
    );

    observer.observe(containerRef.current);

    return () => observer.disconnect();
  }, [isVisible]);

  return (
    <div
      ref={containerRef}
      className="min-w-0"
    >
      <GlassPanel className="h-full border-app-border/70 p-6 shadow-[0_22px_48px_rgba(0,0,0,0.24)] sm:p-7">
        <div className="flex flex-wrap items-center gap-2.5">
          <BadgeChip tone="cyan">{question.question_id}</BadgeChip>
          <BadgeChip tone="neutral">{formatQuestionType(question.question_type)}</BadgeChip>
          <BadgeChip tone="neutral">{`${question.response_count} responses`}</BadgeChip>
        </div>

        <h3 className="mt-5 text-xl font-medium leading-8 tracking-tight text-app-text sm:text-[1.9rem] sm:leading-[2.6rem]">
          {question.question_text}
        </h3>

        <div className="mt-6 rounded-[1.6rem] p-4 sm:p-5 [background:linear-gradient(180deg,rgba(11,16,20,0.9),rgba(8,12,15,0.84))] shadow-[inset_0_0_0_1px_rgba(118,228,255,0.06)]">
          {isVisible ? (
            <QuestionChartSwitch question={question} />
          ) : (
            <div className="flex min-h-[18rem] items-center justify-center rounded-[1.25rem] text-sm text-app-muted">
              Preparing chart...
            </div>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}

const MINIMAL_CHART_FRAME_CLASS =
  "border-0 [background:transparent] p-0 shadow-none [box-shadow:none]";
const BAR_FILL_CLASS =
  "bg-[linear-gradient(180deg,rgba(15,216,255,0.92),rgba(68,142,182,0.84))] shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]";

function QuestionChartSwitch({
  question,
}: {
  question: AnalysisDashboardQuestion;
}) {
  if (question.chart_kind === "word_cloud") {
    return (
      <WordCloudQuestionCard
        terms={question.word_cloud_terms ?? []}
        quotes={question.quotes ?? []}
      />
    );
  }

  if (question.chart_kind === "line") {
    return <LineQuestionChart points={question.line_points ?? []} />;
  }

  if (question.chart_kind === "histogram") {
    return <HistogramQuestionChart bins={question.histogram_bins ?? []} />;
  }

  if (question.chart_kind === "likert") {
    return <BarQuestionChart rows={question.distribution ?? []} kind="likert" />;
  }

  return <BarQuestionChart rows={question.distribution ?? []} kind="categorical" />;
}

function BarQuestionChart({
  rows,
  kind,
}: {
  rows: AnalysisDashboardDistributionRow[];
  kind: "categorical" | "likert";
}) {
  const maxValue = rows.reduce((highest, row) => Math.max(highest, row.count), 0);
  const axis = buildCountAxis(maxValue);
  const reversedTicks = [...axis.ticks].reverse();
  const columnTemplate = `repeat(${Math.max(rows.length, 1)}, minmax(0, 1fr))`;

  return (
    <ChartFrame
      title={kind === "likert" ? "Likert distribution" : "Answer distribution"}
      headerless
      empty={rows.length === 0}
      emptyMessage="No response distribution is available for this question."
      className={MINIMAL_CHART_FRAME_CLASS}
    >
      <div className="grid grid-cols-[2.35rem,minmax(0,1fr)] gap-4">
        <div className="flex h-56 flex-col justify-between pr-1 text-right">
          {reversedTicks.map((tick) => (
            <span
              key={tick}
              className="text-[0.68rem] font-medium text-app-muted/90"
            >
              {formatCountTick(tick)}
            </span>
          ))}
        </div>

        <div className="space-y-3">
          <div className="relative h-56">
            <div className="pointer-events-none absolute inset-0">
              {axis.ticks.map((tick) => {
                const ratio = axis.max > 0 ? tick / axis.max : 0;
                return (
                  <div
                    key={`guide-${tick}`}
                    className="absolute inset-x-0 border-t border-white/6"
                    style={{ bottom: `${ratio * 100}%` }}
                  />
                );
              })}
            </div>

            <div
              className="relative grid h-full items-end gap-3 pb-1"
              style={{ gridTemplateColumns: columnTemplate }}
            >
              {rows.map((row) => {
                const barHeight = axis.max > 0 ? (row.count / axis.max) * 100 : 0;
                return (
                  <div
                    key={row.label}
                    className="flex h-full min-w-0 flex-col justify-end"
                  >
                    <div className="flex h-full w-full items-end">
                      {row.count > 0 ? (
                        <div
                          className={cn(
                            "relative flex w-full items-start justify-center rounded-t-[1rem] rounded-b-[0.2rem] border border-app-border/25 px-2 pt-2.5 transition",
                            BAR_FILL_CLASS
                          )}
                          style={{
                            height: `${barHeight}%`,
                          }}
                        >
                          <span className="text-sm font-semibold text-white/95">
                            {row.count}
                          </span>
                        </div>
                      ) : (
                        <div className="w-full" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div
            className="grid items-start gap-3"
            style={{ gridTemplateColumns: columnTemplate }}
          >
            {rows.map((row) => (
              <div
                key={`${row.label}-label`}
                className="min-w-0 text-center"
              >
                <div className="text-sm leading-6 text-app-text">
                  {row.label}
                </div>
                <div className="mt-2 text-xs text-app-muted">{`${row.percentage.toFixed(1)}%`}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </ChartFrame>
  );
}

function HistogramQuestionChart({
  bins,
}: {
  bins: AnalysisDashboardHistogramBin[];
}) {
  const rows: AnalysisDashboardDistributionRow[] = bins.map((bin) => ({
    label: bin.label,
    count: bin.count,
    percentage: 0,
  }));
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  const withPercentages = rows.map((row) => ({
    ...row,
    percentage: total > 0 ? (row.count / total) * 100 : 0,
  }));
  return <BarQuestionChart rows={withPercentages} kind="categorical" />;
}

function LineQuestionChart({
  points,
}: {
  points: AnalysisDashboardLinePoint[];
}) {
  const maxValue = points.reduce((highest, point) => Math.max(highest, point.count), 0);
  const minValue = 0;
  const chartWidth = 720;
  const chartHeight = 220;
  const xStep = points.length > 1 ? chartWidth / (points.length - 1) : chartWidth / 2;
  const linePoints = points
    .map((point, index) => {
      const x = points.length > 1 ? index * xStep : chartWidth / 2;
      const ratio = maxValue > minValue ? (point.count - minValue) / (maxValue - minValue) : 1;
      const y = chartHeight - ratio * (chartHeight - 24) - 12;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <ChartFrame
      title="Trend over ordered values"
      headerless
      empty={points.length === 0}
      emptyMessage="No ordered trend data is available for this question."
      className={MINIMAL_CHART_FRAME_CLASS}
    >
      <div className="space-y-4">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="h-60 w-full overflow-visible"
          preserveAspectRatio="none"
        >
          <polyline
            fill="none"
            stroke="rgba(224,229,234,0.92)"
            strokeWidth="4"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={linePoints}
          />
          {points.map((point, index) => {
            const x = points.length > 1 ? index * xStep : chartWidth / 2;
            const ratio = maxValue > minValue ? (point.count - minValue) / (maxValue - minValue) : 1;
            const y = chartHeight - ratio * (chartHeight - 24) - 12;
            return (
              <circle
                key={`${point.label}-${index}`}
                cx={x}
                cy={y}
                r="6"
                fill="rgba(180,186,194,1)"
                stroke="rgba(255,255,255,0.7)"
                strokeWidth="2"
              />
            );
          })}
        </svg>

        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {points.map((point) => (
            <div
              key={point.label}
              className="rounded-[1rem] border border-app-border [background:var(--status-neutral-bg)] px-3 py-3"
            >
              <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
                {point.label}
              </div>
              <div className="mt-2 text-sm text-app-text">{point.count}</div>
            </div>
          ))}
        </div>
      </div>
    </ChartFrame>
  );
}

function WordCloudQuestionCard({
  terms,
  quotes,
}: {
  terms: AnalysisDashboardWordCloudTerm[];
  quotes: AnalysisDashboardQuote[];
}) {
  const [showDetails, setShowDetails] = useState(false);
  const palette = [
    "text-[#6d7d1f]",
    "text-[#f0a400]",
    "text-[#c85f1a]",
    "text-[#5d1f4e]",
    "text-[#d9dde3]",
    "text-[#8a6f33]",
  ];
  const cloudTerms = [...terms]
    .sort((left, right) => right.weight - left.weight)
    .slice(0, WORD_CLOUD_SLOTS.length);

  return (
    <ChartFrame
      title="Themes and example quotes"
      headerless
      empty={terms.length === 0 && quotes.length === 0}
      emptyMessage="No open-text responses are available for this question."
      className={MINIMAL_CHART_FRAME_CLASS}
    >
      <div className="space-y-5">
        <div className="relative h-56 overflow-hidden rounded-[1.15rem] border border-white/6 [background:radial-gradient(circle_at_50%_46%,rgba(255,255,255,0.03),rgba(10,14,18,0.88)_70%)] p-4">
          {cloudTerms.map((term, index) => {
            const slot = WORD_CLOUD_SLOTS[index % WORD_CLOUD_SLOTS.length];
            const fontSize = Math.max(
              0.72,
              0.78 + term.weight * 1.65 - Math.max(term.term.length - 10, 0) * 0.02
            );
            return (
              <span
                key={term.term}
                className={cn(
                  "absolute whitespace-nowrap font-semibold transition",
                  palette[index % palette.length]
                )}
                style={{
                  left: `${slot.x}%`,
                  top: `${slot.y}%`,
                  transform: `translate(-50%, -50%) rotate(${slot.rotate}deg)`,
                  fontSize: `${fontSize}rem`,
                  lineHeight: 1,
                  opacity: 0.94,
                }}
              >
                {term.term}
              </span>
            );
          })}
        </div>

        {quotes.length > 0 ? (
          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={() => setShowDetails((current) => !current)}
            >
              {showDetails ? "Hide Details" : "Detail Responses"}
            </Button>
          </div>
        ) : null}

        {showDetails ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {quotes.map((quote, index) => (
              <div
                key={`${quote.text}-${index}`}
                className="rounded-[1rem] border border-white/6 [background:var(--status-neutral-bg)] p-4"
              >
                <div className="text-sm leading-7 text-app-text">“{quote.text}”</div>
                {(quote.model || quote.respondent_id) ? (
                  <div className="mt-3 text-xs uppercase tracking-[0.18em] text-app-muted">
                    {[quote.model, quote.respondent_id].filter(Boolean).join(" • ")}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </ChartFrame>
  );
}

function buildCountAxis(maxValue: number) {
  const safeMax = Math.max(1, maxValue);
  const step = Math.max(1, getNiceStep(safeMax / 4));
  const axisMax = Math.max(step, Math.ceil(safeMax / step) * step);
  const ticks: number[] = [];

  for (let value = 0; value <= axisMax; value += step) {
    ticks.push(value);
  }

  if (ticks[ticks.length - 1] !== axisMax) {
    ticks.push(axisMax);
  }

  return {
    max: axisMax,
    ticks,
  };
}

function getNiceStep(value: number) {
  if (!Number.isFinite(value) || value <= 1) {
    return 1;
  }

  const exponent = Math.floor(Math.log10(value));
  const magnitude = 10 ** exponent;
  const fraction = value / magnitude;

  if (fraction <= 1) {
    return magnitude;
  }
  if (fraction <= 2) {
    return 2 * magnitude;
  }
  if (fraction <= 5) {
    return 5 * magnitude;
  }
  return 10 * magnitude;
}

function formatCountTick(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatQuestionType(questionType?: string) {
  const normalized = String(questionType || "unknown").replaceAll("_", " ");
  return normalized
    .split(" ")
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}
