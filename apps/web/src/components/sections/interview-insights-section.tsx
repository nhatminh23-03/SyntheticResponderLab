"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";

import { BadgeChip } from "@/components/ui/badge-chip";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import {
  InterviewChatMessage,
  InterviewInsightsPayload,
  InterviewPair,
  InterviewRunPayload,
  InterviewTheme,
  getInterviewInsights,
  getLatestInterviewRun,
  sendInterviewChatMessage,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";

type SentimentTone = "positive" | "neutral" | "negative";
type TranscriptSource = "model_a" | "model_b";

const SENTIMENT_STYLES: Record<SentimentTone, string> = {
  positive: "border-emerald-400/25 bg-emerald-400/8 text-emerald-400",
  neutral: "border-white/[0.12] bg-white/[0.04] text-app-muted",
  negative: "border-red-400/25 bg-red-400/8 text-red-400",
};

function formatModelLabel(model: string | null | undefined) {
  return model?.split("/").pop() ?? "Unknown";
}

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
            <p className="text-xs italic leading-5 text-app-text">
              &ldquo;{theme.representative_quote}&rdquo;
            </p>
            {theme.quote_persona_id && (
              <p className="mt-1 text-[0.62rem] text-app-muted">- {theme.quote_persona_id}</p>
            )}
          </blockquote>
        )}
      </GlassPanel>
    </motion.div>
  );
}

function SentimentSummary({ themes }: { themes: InterviewTheme[] }) {
  const counts = { positive: 0, neutral: 0, negative: 0 };
  for (const theme of themes) {
    const sentiment = (theme.sentiment as SentimentTone) ?? "neutral";
    counts[sentiment] = (counts[sentiment] ?? 0) + 1;
  }

  return (
    <div className="flex gap-4">
      {(["positive", "neutral", "negative"] as SentimentTone[]).map((sentiment) => (
        <div key={sentiment} className="text-center">
          <p
            className={cn(
              "text-xl font-bold",
              sentiment === "positive" && "text-emerald-400",
              sentiment === "neutral" && "text-app-muted",
              sentiment === "negative" && "text-red-400"
            )}
          >
            {counts[sentiment]}
          </p>
          <p className="text-[0.62rem] uppercase tracking-[0.1em] text-app-muted">{sentiment}</p>
        </div>
      ))}
    </div>
  );
}

function ChatMessageBubble({ message }: { message: InterviewChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6",
          isUser
            ? "border border-app-cyan/25 bg-app-cyan/10 text-app-text"
            : "border border-white/[0.08] bg-white/[0.04] text-app-muted"
        )}
      >
        <p className="mb-1 text-[0.62rem] uppercase tracking-[0.12em] text-app-muted">
          {isUser ? "Researcher" : "Persona"}
        </p>
        <p>{message.content}</p>
      </div>
    </div>
  );
}

function TranscriptSourceButton({
  active,
  label,
  model,
  onClick,
}: {
  active: boolean;
  label: string;
  model: string | null | undefined;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-[0.68rem] uppercase tracking-[0.12em] transition",
        active
          ? "border-app-cyan/35 bg-app-cyan/10 text-app-text"
          : "border-white/[0.08] bg-white/[0.03] text-app-muted hover:text-app-text"
      )}
    >
      {label}: {formatModelLabel(model)}
    </button>
  );
}

export function InterviewInsightsSection() {
  const { studyId, study } = useStudy();

  const [insights, setInsights] = useState<InterviewInsightsPayload | null>(null);
  const [latestRun, setLatestRun] = useState<InterviewRunPayload | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const [transcriptSource, setTranscriptSource] = useState<TranscriptSource>("model_a");
  const [chatMessages, setChatMessages] = useState<InterviewChatMessage[]>([]);
  const [chatDraft, setChatDraft] = useState("");
  const [chatError, setChatError] = useState<string | null>(null);
  const [isSendingChat, setIsSendingChat] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      if (!studyId) {
        if (!cancelled) {
          setInsights(null);
          setLatestRun(null);
          setSelectedPersonaId("");
          setErrorMsg(null);
        }
        return;
      }

      setIsLoading(true);
      setErrorMsg(null);

      const [insightsResult, latestRunResult] = await Promise.allSettled([
        getInterviewInsights(studyId),
        getLatestInterviewRun(studyId),
      ]);
      if (cancelled) {
        return;
      }

      const loadErrors: string[] = [];
      if (insightsResult.status === "fulfilled") {
        setInsights(insightsResult.value);
      } else {
        setInsights(null);
        loadErrors.push(
          insightsResult.reason instanceof Error
            ? insightsResult.reason.message
            : "Insights load failed."
        );
      }

      if (latestRunResult.status === "fulfilled") {
        setLatestRun(latestRunResult.value);
      } else {
        setLatestRun(null);
        loadErrors.push(
          latestRunResult.reason instanceof Error
            ? latestRunResult.reason.message
            : "Latest interview run load failed."
        );
      }

      setErrorMsg(loadErrors[0] ?? null);
      setIsLoading(false);
    }

    void hydrate();
    return () => {
      cancelled = true;
    };
  }, [studyId, study?.updated_at]);

  const themes = insights?.themes ?? [];
  const pairs = latestRun?.pairs ?? [];

  useEffect(() => {
    if (!pairs.length) {
      setSelectedPersonaId("");
      return;
    }

    if (!pairs.some((pair) => pair.persona_id === selectedPersonaId)) {
      setSelectedPersonaId(pairs[0]?.persona_id ?? "");
    }
  }, [pairs, selectedPersonaId]);

  useEffect(() => {
    setChatMessages([]);
    setChatDraft("");
    setChatError(null);
  }, [selectedPersonaId, transcriptSource]);

  const selectedPair = useMemo<InterviewPair | null>(
    () => pairs.find((pair) => pair.persona_id === selectedPersonaId) ?? null,
    [pairs, selectedPersonaId]
  );

  const selectedTranscript = selectedPair?.[transcriptSource] ?? null;
  const transcriptAnswers = useMemo(
    () =>
      Object.entries(selectedTranscript?.answers ?? {}).filter(
        ([questionId, answer]) => questionId !== "additional_thoughts" && Boolean(answer)
      ),
    [selectedTranscript]
  );

  async function handleChatSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const prompt = chatDraft.trim();
    if (!studyId || !selectedPersonaId || !prompt) {
      return;
    }

    const priorMessages = chatMessages;
    const optimisticMessages = [...priorMessages, { role: "user", content: prompt } as const];

    setChatMessages(optimisticMessages);
    setChatDraft("");
    setChatError(null);
    setIsSendingChat(true);

    try {
      const response = await sendInterviewChatMessage(studyId, {
        persona_id: selectedPersonaId,
        prompt,
        messages: priorMessages,
        transcript_source: transcriptSource,
      });

      setChatMessages([
        ...optimisticMessages,
        { role: "assistant", content: response.reply },
      ]);
    } catch (error) {
      setChatMessages(priorMessages);
      setChatDraft(prompt);
      setChatError(error instanceof Error ? error.message : "Interview chat failed.");
    } finally {
      setIsSendingChat(false);
    }
  }

  return (
    <SectionWrapper id="interview-insights" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={12}
              eyebrow="Interview Insights"
              title="Recurring themes, representative quotes, and persona follow-up chat."
              description="The LLM extracts shared themes across the interview corpus, then lets you continue the conversation with any persona as if you were asking follow-up interview questions."
            />
          </RevealOnScroll>

          {isLoading && (
            <RevealOnScroll delay={0.04}>
              <GlassPanel className="p-6">
                <p className="text-sm text-app-muted">
                  Loading interview insights and transcript context...
                </p>
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

          {!isLoading && themes.length > 0 && (
            <div className="space-y-4">
              {themes.map((theme, index) => (
                <ThemeCard key={theme.label} theme={theme} index={index} />
              ))}
            </div>
          )}

          {latestRun?.status === "completed" && pairs.length > 0 && (
            <RevealOnScroll delay={0.08}>
              <GlassPanel className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs uppercase tracking-[0.14em] text-app-muted">
                      Continue The Interview
                    </p>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-app-muted">
                      Pick a persona and continue the interview in character. Changing persona or
                      transcript source resets the current conversation so each thread stays grounded
                      in one respondent.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setChatMessages([]);
                      setChatDraft("");
                      setChatError(null);
                    }}
                    className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-[0.68rem] uppercase tracking-[0.12em] text-app-muted transition hover:text-app-text"
                  >
                    Clear conversation
                  </button>
                </div>

                <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
                  <div className="space-y-4">
                    <div>
                      <label className="mb-2 block text-[0.68rem] uppercase tracking-[0.12em] text-app-muted">
                        Persona
                      </label>
                      <select
                        value={selectedPersonaId}
                        onChange={(event) => setSelectedPersonaId(event.target.value)}
                        className="w-full rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-app-text focus:border-app-cyan/30 focus:outline-none"
                      >
                        {pairs.map((pair) => {
                          const fitTier = String(pair.persona?.fit_tier ?? "?");
                          const segment = String(pair.persona?.segment_label ?? "?");
                          return (
                            <option key={pair.persona_id} value={pair.persona_id}>
                              {pair.persona_id} - {fitTier} - {segment}
                            </option>
                          );
                        })}
                      </select>
                    </div>

                    <div>
                      <p className="mb-2 text-[0.68rem] uppercase tracking-[0.12em] text-app-muted">
                        Transcript Source
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <TranscriptSourceButton
                          active={transcriptSource === "model_a"}
                          label="Model A"
                          model={selectedPair?.model_a.model}
                          onClick={() => setTranscriptSource("model_a")}
                        />
                        <TranscriptSourceButton
                          active={transcriptSource === "model_b"}
                          label="Model B"
                          model={selectedPair?.model_b.model}
                          onClick={() => setTranscriptSource("model_b")}
                        />
                      </div>
                    </div>

                    {selectedPair && (
                      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                        <p className="text-[0.68rem] uppercase tracking-[0.12em] text-app-muted">
                          Persona Snapshot
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <BadgeChip>{String(selectedPair.persona?.fit_tier ?? "unknown")} fit</BadgeChip>
                          <BadgeChip>{String(selectedPair.persona?.segment_label ?? "unknown segment")}</BadgeChip>
                          <BadgeChip>{String(selectedPair.persona?.age_bucket ?? "unknown age")}</BadgeChip>
                        </div>
                        <p className="mt-3 text-xs leading-5 text-app-muted">
                          {String(
                            selectedPair.persona?.likely_use_case ??
                              "Use the transcript below as the main grounding context for follow-up questions."
                          )}
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="space-y-4">
                    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-[0.68rem] uppercase tracking-[0.12em] text-app-muted">
                          Prior Transcript Context
                        </p>
                        <span className="text-[0.68rem] uppercase tracking-[0.12em] text-app-muted">
                          {formatModelLabel(selectedTranscript?.model)}
                        </span>
                      </div>
                      <div className="mt-3 max-h-48 space-y-3 overflow-y-auto pr-1">
                        {transcriptAnswers.slice(0, 4).map(([questionId, answer]) => (
                          <div key={questionId}>
                            <p className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-app-muted">
                              {questionId}
                            </p>
                            <p className="mt-1 text-xs leading-5 text-app-muted">{answer}</p>
                          </div>
                        ))}
                        {!transcriptAnswers.length && (
                          <p className="text-xs text-app-muted">
                            No saved transcript answers for this persona yet.
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-white/[0.08] bg-[rgba(8,11,15,0.55)] p-4">
                      <div className="max-h-[24rem] space-y-3 overflow-y-auto pr-1">
                        {chatMessages.length === 0 ? (
                          <p className="text-sm leading-6 text-app-muted">
                            Ask a follow-up like &ldquo;What would make you trust the install
                            process more?&rdquo; or &ldquo;How would your spouse react to this
                            purchase?&rdquo;
                          </p>
                        ) : (
                          chatMessages.map((message, index) => (
                            <ChatMessageBubble key={`${message.role}-${index}`} message={message} />
                          ))
                        )}
                        {isSendingChat && (
                          <div className="flex justify-start">
                            <div className="rounded-2xl border border-white/[0.08] bg-white/[0.04] px-4 py-3 text-sm text-app-muted">
                              Persona is responding...
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    <form className="space-y-3" onSubmit={handleChatSubmit}>
                      <textarea
                        value={chatDraft}
                        onChange={(event) => setChatDraft(event.target.value)}
                        rows={4}
                        placeholder="Ask this persona a follow-up interview question..."
                        className="w-full resize-y rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-app-text placeholder-app-muted focus:border-app-cyan/30 focus:outline-none"
                      />
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-xs text-app-muted">
                          Replies use the saved transcript plus persona context from the latest
                          interview run.
                        </p>
                        <button
                          type="submit"
                          disabled={!selectedPersonaId || !chatDraft.trim() || isSendingChat}
                          className={cn(
                            "inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold transition",
                            !selectedPersonaId || !chatDraft.trim() || isSendingChat
                              ? "cursor-not-allowed border border-white/[0.08] bg-[rgba(17,24,29,0.88)] text-app-muted opacity-60"
                              : "border border-app-cyan/35 bg-[linear-gradient(135deg,rgba(118,228,255,0.18),rgba(15,216,255,0.10))] text-app-text hover:-translate-y-0.5"
                          )}
                        >
                          {isSendingChat ? "Sending..." : "Send follow-up"}
                        </button>
                      </div>
                    </form>

                    {chatError && <p className="text-sm text-red-400">{chatError}</p>}
                  </div>
                </div>
              </GlassPanel>
            </RevealOnScroll>
          )}
        </div>

        <div className="space-y-4 xl:sticky xl:top-[calc(var(--nav-height)+1.5rem)]">
          {themes.length > 0 && (
            <RevealOnScroll delay={0.06}>
              <GlassPanel className="p-5">
                <p className="mb-3 text-xs uppercase tracking-[0.14em] text-app-muted">
                  Sentiment Distribution
                </p>
                <SentimentSummary themes={themes} />
              </GlassPanel>
            </RevealOnScroll>
          )}

          {insights?.grounding_corpus_average != null && (
            <RevealOnScroll delay={0.08}>
              <GlassPanel className="p-5">
                <p className="mb-1 text-xs uppercase tracking-[0.14em] text-app-muted">
                  Grounding Score
                </p>
                <p
                  className={cn(
                    "text-2xl font-bold tabular-nums",
                    insights.grounding_passes_threshold ? "text-emerald-400" : "text-amber-400"
                  )}
                >
                  {Math.round((insights.grounding_corpus_average ?? 0) * 100)}%
                </p>
                <p className="mt-0.5 text-xs text-app-muted">
                  {insights.grounding_passes_threshold
                    ? "Batch passed threshold"
                    : "Below threshold - treat with caution"}
                </p>
              </GlassPanel>
            </RevealOnScroll>
          )}

          <RevealOnScroll delay={0.1}>
            <GlassPanel className="p-5">
              <p className="mb-3 text-xs uppercase tracking-[0.14em] text-app-muted">
                About This Section
              </p>
              <p className="text-xs leading-5 text-app-muted">
                Theme extraction summarizes the Model A corpus. Persona follow-up chat continues one
                selected respondent in character using the saved transcript and persona profile from
                Interview Synthesis.
              </p>
            </GlassPanel>
          </RevealOnScroll>

          {(latestRun?.persona_count ?? insights?.persona_count) != null && (
            <RevealOnScroll delay={0.12}>
              <div className="flex justify-center gap-6 px-1 py-3">
                <div className="text-center">
                  <p className="text-2xl font-bold text-app-text">
                    {latestRun?.persona_count ?? insights?.persona_count}
                  </p>
                  <p className="text-[0.62rem] uppercase tracking-[0.1em] text-app-muted">
                    Interviews
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-app-text">{themes.length}</p>
                  <p className="text-[0.62rem] uppercase tracking-[0.1em] text-app-muted">
                    Themes
                  </p>
                </div>
              </div>
            </RevealOnScroll>
          )}
        </div>
      </div>
    </SectionWrapper>
  );
}
