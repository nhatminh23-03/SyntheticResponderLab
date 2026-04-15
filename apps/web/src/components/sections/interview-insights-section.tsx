"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { BadgeChip } from "@/components/ui/badge-chip";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import {
  InterviewInsightsPayload,
  InterviewTheme,
  getInterviewInsights,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";

type SentimentTone = "positive" | "neutral" | "negative";

const SENTIMENT_STYLES: Record<SentimentTone, string> = {
  positive: "border-emerald-400/25 bg-emerald-400/8 text-emerald-400",
  neutral: "border-white/[0.12] bg-white/[0.04] text-app-muted",
  negative: "border-red-400/25 bg-red-400/8 text-red-400",
};

function ThemeCard({ theme, index }: { theme: InterviewTheme; index: number }) {
  const sentiment: SentimentTone = (theme.sentiment as SentimentTone) ?? "neutral";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4 }}
    >
      <GlassPanel className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-app-text">{theme.label}</p>
            <p className="mt-0.5 text-xs text-app-muted">
              Mentioned by ~{theme.count} interview{theme.count !== 1 ? "s" : ""}
            </p>
          </div>
          <span
            className={cn(
              "shrink-0 rounded-full border px-2.5 py-0.5 text-[0.6rem] uppercase tracking-[0.12em]",
              SENTIMENT_STYLES[sentiment]
            )}
          >
            {sentiment}
          </span>
        </div>

        <p className="mt-3 text-sm leading-6 text-app-muted">{theme.synthesis}</p>

        {theme.representative_quote && (
          <blockquote className="mt-3 border-l-2 border-app-cyan/30 pl-3">
            <p className="text-xs italic leading-5 text-app-text">&ldquo;{theme.representative_quote}&rdquo;</p>
            {theme.quote_persona_id && (
              <p className="mt-1 text-[0.62rem] text-app-muted">— {theme.quote_persona_id}</p>
            )}
          </blockquote>
        )}
      </GlassPanel>
    </motion.div>
  );
}

function SentimentSummary({ themes }: { themes: InterviewTheme[] }) {
  const counts = { positive: 0, neutral: 0, negative: 0 };
  for (const t of themes) {
    const s = (t.sentiment as SentimentTone) ?? "neutral";
    counts[s] = (counts[s] ?? 0) + 1;
  }
  const total = themes.length;

  return (
    <div className="flex gap-4">
      {(["positive", "neutral", "negative"] as SentimentTone[]).map((s) => (
        <div key={s} className="text-center">
          <p
            className={cn(
              "text-xl font-bold",
              s === "positive" && "text-emerald-400",
              s === "neutral" && "text-app-muted",
              s === "negative" && "text-red-400"
            )}
          >
            {counts[s]}
          </p>
          <p className="text-[0.62rem] uppercase tracking-[0.1em] text-app-muted">{s}</p>
        </div>
      ))}
    </div>
  );
}

export function InterviewInsightsSection() {
  const { studyId, study } = useStudy();

  const [insights, setInsights] = useState<InterviewInsightsPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      if (!studyId) {
        setInsights(null);
        return;
      }
      setIsLoading(true);
      try {
        const result = await getInterviewInsights(studyId);
        if (!cancelled) setInsights(result);
      } catch (e) {
        if (!cancelled) setErrorMsg(e instanceof Error ? e.message : "Insights load failed.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    void hydrate();
    return () => { cancelled = true; };
  }, [studyId, study?.updated_at]);

  const themes = insights?.themes ?? [];

  return (
    <SectionWrapper id="interview-insights" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={12}
              eyebrow="Interview Insights"
              title="Recurring themes and representative quotes across the interview corpus."
              description="The LLM identifies 3–6 distinct themes that appear across multiple interviews, surfaces the most representative quote per theme, and labels overall sentiment."
            />
          </RevealOnScroll>

          {/* Status / loading */}
          {isLoading && (
            <RevealOnScroll delay={0.04}>
              <GlassPanel className="p-6">
                <p className="text-sm text-app-muted">Extracting themes from interview corpus…</p>
              </GlassPanel>
            </RevealOnScroll>
          )}

          {errorMsg && (
            <RevealOnScroll delay={0.04}>
              <div className="rounded-xl border border-red-400/20 bg-red-400/5 p-4">
                <p className="text-sm text-red-400">{errorMsg}</p>
              </div>
            </RevealOnScroll>
          )}

          {!isLoading && insights && !insights.available && (
            <RevealOnScroll delay={0.04}>
              <GlassPanel className="p-6">
                <p className="text-sm text-app-muted">
                  {insights.message ?? "Complete Interview Synthesis first to generate insights."}
                </p>
              </GlassPanel>
            </RevealOnScroll>
          )}

          {/* Theme cards */}
          {!isLoading && themes.length > 0 && (
            <div className="space-y-4">
              {themes.map((theme, i) => (
                <ThemeCard key={theme.label} theme={theme} index={i} />
              ))}
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4 lg:sticky lg:top-[calc(var(--nav-height)+1.5rem)]">
          {themes.length > 0 && (
            <RevealOnScroll delay={0.06}>
              <GlassPanel className="p-5">
                <p className="mb-3 text-xs uppercase tracking-[0.14em] text-app-muted">Sentiment Distribution</p>
                <SentimentSummary themes={themes} />
              </GlassPanel>
            </RevealOnScroll>
          )}

          {insights?.grounding_corpus_average != null && (
            <RevealOnScroll delay={0.08}>
              <GlassPanel className="p-5">
                <p className="mb-1 text-xs uppercase tracking-[0.14em] text-app-muted">Grounding Score</p>
                <p
                  className={cn(
                    "text-2xl font-bold tabular-nums",
                    (insights.grounding_passes_threshold ?? false)
                      ? "text-emerald-400"
                      : "text-amber-400"
                  )}
                >
                  {Math.round((insights.grounding_corpus_average ?? 0) * 100)}%
                </p>
                <p className="mt-0.5 text-xs text-app-muted">
                  {insights.grounding_passes_threshold
                    ? "Batch passed threshold"
                    : "Below threshold — treat with caution"}
                </p>
              </GlassPanel>
            </RevealOnScroll>
          )}

          <RevealOnScroll delay={0.1}>
            <GlassPanel className="p-5">
              <p className="mb-3 text-xs uppercase tracking-[0.14em] text-app-muted">About these insights</p>
              <p className="text-xs leading-5 text-app-muted">
                Themes are extracted by LLM from the Model A transcripts, grounded against your Research Brief.
                Quotes are verbatim from individual persona responses.
                Always cross-check surprising themes against the raw transcript pairs in Interview Synthesis.
              </p>
            </GlassPanel>
          </RevealOnScroll>

          {insights?.persona_count != null && (
            <RevealOnScroll delay={0.12}>
              <div className="flex justify-center gap-6 px-1 py-3">
                <div className="text-center">
                  <p className="text-2xl font-bold text-app-text">{insights.persona_count}</p>
                  <p className="text-[0.62rem] uppercase tracking-[0.1em] text-app-muted">Interviews</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-app-text">{themes.length}</p>
                  <p className="text-[0.62rem] uppercase tracking-[0.1em] text-app-muted">Themes</p>
                </div>
              </div>
            </RevealOnScroll>
          )}
        </div>
      </div>
    </SectionWrapper>
  );
}
