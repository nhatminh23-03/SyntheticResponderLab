"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import {
  InterviewGroundingReport,
  InterviewPersonaScore,
  InterviewRunPayload,
  InterviewSynthesisConfig,
  getInterviewSynthesis,
  getLatestInterviewRun,
  saveInterviewSynthesisConfig,
  startInterviewRun,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { useStudy } from "@/providers/study-provider";

const DIMENSIONS = [
  { key: "purchase_intent", label: "Purchase Intent" },
  { key: "primary_objection", label: "Primary Objection" },
  { key: "fit_tier_alignment", label: "Fit-Tier Alignment" },
  { key: "use_case_specificity", label: "Use-Case Specificity" },
] as const;

type DimensionKey = (typeof DIMENSIONS)[number]["key"];

function scoreTone(score: number): "success" | "warning" | "error" {
  if (score >= 0.67) return "success";
  if (score >= 0.5) return "warning";
  return "error";
}

function GroundingBar({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.round((value / max) * 100);
  const tone = scoreTone(value);
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={cn(
            "absolute inset-y-0 left-0 rounded-full",
            tone === "success" && "bg-emerald-400",
            tone === "warning" && "bg-amber-400",
            tone === "error" && "bg-red-400"
          )}
        />
      </div>
      <span className="w-9 shrink-0 text-right text-xs tabular-nums text-app-muted">
        {pct}%
      </span>
    </div>
  );
}

function GroundingReportCard({
  report,
  onContinue,
}: {
  report: InterviewGroundingReport;
  onContinue: () => void;
}) {
  const tone = scoreTone(report.corpus_average);
  const [expanded, setExpanded] = useState(false);

  return (
    <GlassPanel className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-app-muted">STAMP Grounding Score</p>
          <p
            className={cn(
              "mt-1 text-4xl font-bold tabular-nums",
              tone === "success" && "text-emerald-400",
              tone === "warning" && "text-amber-400",
              tone === "error" && "text-red-400"
            )}
          >
            {Math.round(report.corpus_average * 100)}%
          </p>
          <p className="mt-1 text-xs text-app-muted">
            Corpus-level agreement (threshold {Math.round(report.threshold * 100)}%)
          </p>
        </div>

        <span
          className={cn(
            "rounded-full border px-3 py-1 text-[0.62rem] uppercase tracking-[0.12em]",
            report.passes_threshold
              ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-400"
              : "border-red-400/25 bg-red-400/10 text-red-400"
          )}
        >
          {report.passes_threshold ? "Passes threshold" : "Below threshold"}
        </span>
      </div>

      {/* Per-dimension bars */}
      <div className="mt-5 space-y-3">
        {DIMENSIONS.map(({ key, label }) => (
          <div key={key}>
            <div className="mb-1 flex justify-between text-xs text-app-muted">
              <span>{label}</span>
              <span>{Math.round((report.per_dimension_avg[key as DimensionKey] ?? 0) * 100)}%</span>
            </div>
            <GroundingBar value={report.per_dimension_avg[key as DimensionKey] ?? 0} />
          </div>
        ))}
      </div>

      {/* Flagged personas */}
      {report.flagged_persona_ids.length > 0 && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-app-muted underline underline-offset-2 hover:text-app-text"
          >
            {expanded ? "Hide" : "Show"} {report.flagged_persona_ids.length} flagged persona(s)
          </button>
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-2 overflow-hidden"
              >
                <div className="flex flex-wrap gap-1.5">
                  {report.flagged_persona_ids.map((id) => (
                    <span
                      key={id}
                      className="rounded-full border border-red-400/20 bg-red-400/10 px-2 py-0.5 text-[0.62rem] text-red-400"
                    >
                      {id}
                    </span>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* CTA */}
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onContinue}
          className="inline-flex items-center gap-2 rounded-full border border-app-cyan/40 bg-[linear-gradient(135deg,rgba(118,228,255,0.18),rgba(15,216,255,0.10))] px-5 py-2 text-sm font-semibold text-app-text transition hover:-translate-y-0.5"
        >
          Continue to Research Brief →
        </button>
        {!report.passes_threshold && (
          <p className="text-xs text-amber-400">
            Score below threshold — interviews are available but accuracy may be limited.
          </p>
        )}
      </div>
    </GlassPanel>
  );
}

function TranscriptPairCard({ pair, index }: { pair: NonNullable<InterviewRunPayload["pairs"]>[number]; index: number }) {
  const [open, setOpen] = useState(false);
  const personaScore = pair.persona as Record<string, unknown>;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-sm text-app-text">
          #{index + 1} — {pair.persona_id}
          <span className="ml-2 text-xs text-app-muted">
            fit={String(personaScore?.fit_tier ?? "?")} · segment={String(personaScore?.segment_label ?? "?")}
          </span>
        </span>
        <span className="text-xs text-app-muted">{open ? "▲" : "▼"}</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="grid gap-4 border-t border-white/[0.05] p-4 md:grid-cols-2">
              {(["model_a", "model_b"] as const).map((key) => {
                const t = pair[key];
                return (
                  <div key={key}>
                    <p className="mb-2 text-[0.68rem] uppercase tracking-[0.14em] text-app-muted">
                      {t.model.split("/").pop()}
                      {t.error && <span className="ml-2 text-red-400">(error)</span>}
                    </p>
                    <div className="space-y-2">
                      {Object.entries(t.answers).map(([qid, ans]) => {
                        if (qid === "additional_thoughts") return null;
                        return (
                          <div key={qid}>
                            <p className="text-[0.68rem] font-semibold text-app-muted">{qid}</p>
                            <p className="mt-0.5 text-xs leading-5 text-app-text">{ans}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function InterviewSynthesisSection() {
  const { studyId, study } = useStudy();
  const { scrollToSection } = useSectionRegistry();

  const [latestRun, setLatestRun] = useState<InterviewRunPayload | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showPairs, setShowPairs] = useState(false);

  // Config state
  const [customQuestionsText, setCustomQuestionsText] = useState("");
  const [showConfig, setShowConfig] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      if (!studyId) return;
      try {
        const state = await getInterviewSynthesis(studyId);
        if (!cancelled) {
          setLatestRun(state.latest_run ?? null);
          if (state.value?.questions) {
            setCustomQuestionsText(
              state.value.questions.map((q) => `${q.id}: ${q.text}`).join("\n")
            );
          }
        }
      } catch {
        // silently ignore on load
      }
    }
    void hydrate();
    return () => { cancelled = true; };
  }, [studyId, study?.updated_at]);

  function parseQuestions(raw: string) {
    const lines = raw.trim().split("\n").filter((l) => l.trim());
    return lines
      .map((line) => {
        const idx = line.indexOf(":");
        if (idx < 0) return null;
        const id = line.slice(0, idx).trim();
        const text = line.slice(idx + 1).trim();
        return id && text ? { id, text } : null;
      })
      .filter(Boolean) as { id: string; text: string }[];
  }

  async function handleRun() {
    if (!studyId) return;
    setIsRunning(true);
    setErrorMsg(null);
    try {
      const questions = customQuestionsText.trim() ? parseQuestions(customQuestionsText) : undefined;
      if (questions !== undefined && showConfig) {
        await saveInterviewSynthesisConfig(studyId, { questions });
      }
      const run = await startInterviewRun(studyId, questions ? { questions } : undefined);
      setLatestRun(run);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Interview run failed.");
    } finally {
      setIsRunning(false);
    }
  }

  const hasPairs = latestRun?.pairs && latestRun.pairs.length > 0;
  const groundingReport = latestRun?.grounding_report ?? null;

  return (
    <SectionWrapper id="interview-synthesis" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={10}
              eyebrow="Interview"
              title="Generate synthetic depth interviews grounded in your personas."
              description="Both AI models interview every persona independently. A judge LLM then scores agreement across four dimensions — STAMP-style — to flag low-reliability interviews before you rely on them."
            />
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <div className="rounded-[1.45rem] border border-app-gold/20 bg-[rgba(216,186,103,0.08)] px-5 py-4 text-sm leading-6 text-app-gold">
              Dual-model verification: both LLMs interview every persona. A grounding score analogous to Krippendorff&apos;s α flags divergence before you proceed to research insights.
            </div>
          </RevealOnScroll>

          {/* Config toggle */}
          <RevealOnScroll delay={0.06}>
            <GlassPanel className="p-5">
              <button
                type="button"
                onClick={() => setShowConfig((v) => !v)}
                className="mb-3 flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-app-muted hover:text-app-text"
              >
                {showConfig ? "▲" : "▼"} Custom questions (optional)
              </button>

              <AnimatePresence>
                {showConfig && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <p className="mb-2 text-xs text-app-muted">
                      Enter one question per line as <code className="text-app-cyan">ID: Question text</code>.
                      Leave blank to use the 8 default interview questions.
                    </p>
                    <textarea
                      value={customQuestionsText}
                      onChange={(e) => setCustomQuestionsText(e.target.value)}
                      placeholder={"IQ1: How do you currently use this category?\nIQ2: What frustrations do you have?"}
                      rows={6}
                      className="w-full resize-y rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 font-mono text-xs text-app-text placeholder-app-muted focus:border-app-cyan/30 focus:outline-none"
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </GlassPanel>
          </RevealOnScroll>

          {/* Run button */}
          <RevealOnScroll delay={0.08}>
            <div className="flex items-center gap-4">
              <button
                type="button"
                disabled={isRunning || !studyId}
                onClick={handleRun}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-semibold tracking-[0.03em] transition",
                  isRunning || !studyId
                    ? "cursor-not-allowed opacity-50 border border-white/[0.08] bg-[rgba(17,24,29,0.88)] text-app-muted"
                    : "border border-app-gold/40 bg-[linear-gradient(135deg,rgba(216,186,103,0.18),rgba(216,186,103,0.08))] text-app-gold hover:-translate-y-0.5"
                )}
              >
                {isRunning ? (
                  <>
                    <span className="animate-spin">⟳</span> Running interviews…
                  </>
                ) : (
                  <>▶ Run Interviews</>
                )}
              </button>

              {latestRun?.status === "completed" && (
                <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-[0.62rem] uppercase tracking-[0.12em] text-emerald-400">
                  {latestRun.persona_count ?? 0} interviews complete
                </span>
              )}
              {latestRun?.status === "failed" && (
                <span className="rounded-full border border-red-400/25 bg-red-400/10 px-3 py-1 text-[0.62rem] uppercase tracking-[0.12em] text-red-400">
                  Run failed
                </span>
              )}
            </div>

            {errorMsg && (
              <p className="mt-2 text-sm text-red-400">{errorMsg}</p>
            )}
          </RevealOnScroll>

          {/* Grounding report */}
          {latestRun?.status === "completed" && groundingReport && (
            <RevealOnScroll delay={0.1}>
              <GroundingReportCard
                report={groundingReport}
                onContinue={() => scrollToSection("research-brief")}
              />
            </RevealOnScroll>
          )}

          {/* Transcript pairs */}
          {hasPairs && (
            <RevealOnScroll delay={0.12}>
              <div>
                <button
                  type="button"
                  onClick={() => setShowPairs((v) => !v)}
                  className="mb-3 text-sm text-app-muted underline underline-offset-2 hover:text-app-text"
                >
                  {showPairs ? "Hide" : "View"} transcript pairs ({latestRun!.pairs!.length})
                </button>
                <AnimatePresence>
                  {showPairs && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="space-y-2"
                    >
                      {latestRun!.pairs!.map((pair, i) => (
                        <TranscriptPairCard key={pair.persona_id} pair={pair} index={i} />
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </RevealOnScroll>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4 lg:sticky lg:top-[calc(var(--nav-height)+1.5rem)]">
          <RevealOnScroll delay={0.1}>
            <GlassPanel className="p-5">
              <p className="mb-3 text-xs uppercase tracking-[0.14em] text-app-muted">How it works</p>
              <ol className="space-y-2 text-sm text-app-text">
                {[
                  "Both LLMs interview every persona in parallel",
                  "A judge LLM scores agreement on 4 dimensions per persona",
                  "Corpus-level average ≥ 67% = batch passes threshold",
                  "Flagged personas show which dimension drove disagreement",
                  "Proceed to Research Brief to frame your analysis",
                ].map((step, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-0.5 shrink-0 text-xs text-app-cyan">{i + 1}.</span>
                    <span className="text-xs leading-5 text-app-muted">{step}</span>
                  </li>
                ))}
              </ol>
            </GlassPanel>
          </RevealOnScroll>

          {latestRun?.grounding_report && (
            <RevealOnScroll delay={0.14}>
              <GlassPanel className="p-5">
                <p className="mb-2 text-xs uppercase tracking-[0.14em] text-app-muted">Models Used</p>
                <div className="space-y-1 text-xs text-app-text">
                  <p><span className="text-app-muted">Model A:</span> {latestRun.model_a?.split("/").pop()}</p>
                  <p><span className="text-app-muted">Model B:</span> {latestRun.model_b?.split("/").pop()}</p>
                </div>
              </GlassPanel>
            </RevealOnScroll>
          )}
        </div>
      </div>
    </SectionWrapper>
  );
}
