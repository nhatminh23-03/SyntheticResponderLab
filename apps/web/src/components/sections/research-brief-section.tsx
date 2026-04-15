"use client";

import { useEffect, useState } from "react";

import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import {
  ResearchBriefValue,
  getResearchBrief,
  saveResearchBrief,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { useStudy } from "@/providers/study-provider";

const FIT_TIERS = ["strong", "soft", "latent", "edge"] as const;

function TextareaField({
  label,
  hint,
  value,
  onChange,
  rows = 3,
  placeholder,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">
        {label}
      </label>
      {hint && <p className="mb-2 text-xs text-app-muted">{hint}</p>}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        placeholder={placeholder}
        className="w-full resize-y rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-sm text-app-text placeholder-app-muted focus:border-app-cyan/30 focus:outline-none"
      />
    </div>
  );
}

function parseLines(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function toLines(items: string[]): string {
  return items.join("\n");
}

export function ResearchBriefSection() {
  const { studyId, study } = useStudy();
  const { scrollToSection } = useSectionRegistry();

  const [isSaving, setIsSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form fields
  const [primaryQuestion, setPrimaryQuestion] = useState("");
  const [hypothesesText, setHypothesesText] = useState("");
  const [decisionsText, setDecisionsText] = useState("");
  const [focusTiers, setFocusTiers] = useState<string[]>([]);
  const [focusSegmentsText, setFocusSegmentsText] = useState("");
  const [knownContext, setKnownContext] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      if (!studyId) return;
      try {
        const state = await getResearchBrief(studyId);
        if (!cancelled && state.value) {
          const v = state.value;
          setPrimaryQuestion(v.primary_question || "");
          setHypothesesText(toLines(v.hypotheses || []));
          setDecisionsText(toLines(v.decisions_to_inform || []));
          setFocusTiers(v.focus_fit_tiers || []);
          setFocusSegmentsText(toLines(v.focus_segments || []));
          setKnownContext(v.known_context || "");
          setNotes(v.notes || "");
          setSavedAt(state.saved_at);
        }
      } catch {
        // silently ignore
      }
    }
    void hydrate();
    return () => { cancelled = true; };
  }, [studyId, study?.updated_at]);

  function toggleTier(tier: string) {
    setFocusTiers((prev) =>
      prev.includes(tier) ? prev.filter((t) => t !== tier) : [...prev, tier]
    );
  }

  async function handleSave() {
    if (!studyId) return;
    if (!primaryQuestion.trim()) {
      setErrorMsg("Primary question is required.");
      return;
    }
    setIsSaving(true);
    setErrorMsg(null);
    try {
      const payload: Partial<ResearchBriefValue> = {
        primary_question: primaryQuestion.trim(),
        hypotheses: parseLines(hypothesesText),
        decisions_to_inform: parseLines(decisionsText),
        focus_fit_tiers: focusTiers,
        focus_segments: parseLines(focusSegmentsText),
        known_context: knownContext.trim() || null,
        notes: notes.trim() || null,
      };
      const saved = await saveResearchBrief(studyId, payload);
      if (saved) setSavedAt(saved.saved_at);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <SectionWrapper id="research-brief" scrollable contentClassName="relative">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <RevealOnScroll>
            <SectionHeader
              index={11}
              eyebrow="Research Brief"
              title="Frame your research intent before exploring interview insights."
              description="This brief tells the insights layer what question you're trying to answer, what you expect to find, and which decisions the interviews should inform."
            />
          </RevealOnScroll>

          <RevealOnScroll delay={0.04}>
            <GlassPanel className="p-6 space-y-5">
              <TextareaField
                label="Primary Research Question *"
                hint="The single most important question this research needs to answer."
                value={primaryQuestion}
                onChange={setPrimaryQuestion}
                rows={3}
                placeholder="e.g. Which customer segment is most likely to convert within the first 60 days?"
              />

              <TextareaField
                label="Hypotheses"
                hint="What do you expect to find? One hypothesis per line."
                value={hypothesesText}
                onChange={setHypothesesText}
                rows={4}
                placeholder={"Strong-fit personas will cite price as their main barrier.\nAwareness will be lowest among edge-tier respondents."}
              />

              <TextareaField
                label="Decisions to Inform"
                hint="Which product, positioning, or strategy decisions should this research inform? One per line."
                value={decisionsText}
                onChange={setDecisionsText}
                rows={4}
                placeholder={"Whether to launch with a premium or freemium model.\nWhich feature to prioritize in v2."}
              />

              {/* Focus fit tiers */}
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">
                  Focus Fit Tiers
                </label>
                <div className="flex flex-wrap gap-2">
                  {FIT_TIERS.map((tier) => (
                    <button
                      key={tier}
                      type="button"
                      onClick={() => toggleTier(tier)}
                      className={cn(
                        "rounded-full border px-3 py-1 text-xs transition",
                        focusTiers.includes(tier)
                          ? "border-app-cyan/40 bg-app-cyan/10 text-app-cyan"
                          : "border-white/[0.08] text-app-muted hover:text-app-text"
                      )}
                    >
                      {tier}
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-xs text-app-muted">
                  Leave empty to include all tiers in analysis.
                </p>
              </div>

              <TextareaField
                label="Focus Segments"
                hint="Segment labels to prioritise in analysis. One per line."
                value={focusSegmentsText}
                onChange={setFocusSegmentsText}
                rows={2}
                placeholder="e.g. Urban Renters"
              />

              <TextareaField
                label="Known Context"
                hint="Background the analyst should know (previous research, key constraints, etc.)."
                value={knownContext}
                onChange={setKnownContext}
                rows={3}
              />

              <TextareaField
                label="Notes"
                hint="Any other framing notes."
                value={notes}
                onChange={setNotes}
                rows={2}
              />
            </GlassPanel>
          </RevealOnScroll>

          {/* Save / status */}
          <RevealOnScroll delay={0.08}>
            <div className="flex items-center gap-4">
              <button
                type="button"
                disabled={isSaving}
                onClick={handleSave}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-semibold tracking-[0.03em] transition",
                  isSaving
                    ? "cursor-not-allowed opacity-50 border border-white/[0.08] bg-[rgba(17,24,29,0.88)] text-app-muted"
                    : "border border-app-cyan/40 bg-[linear-gradient(135deg,rgba(118,228,255,0.18),rgba(15,216,255,0.10))] text-app-text hover:-translate-y-0.5"
                )}
              >
                {isSaving ? "Saving…" : "Save Brief"}
              </button>

              {savedAt && !errorMsg && (
                <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-[0.62rem] uppercase tracking-[0.12em] text-emerald-400">
                  Brief saved
                </span>
              )}
              {errorMsg && (
                <p className="text-sm text-red-400">{errorMsg}</p>
              )}
            </div>
          </RevealOnScroll>

          {savedAt && (
            <RevealOnScroll delay={0.1}>
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => scrollToSection("interview-insights")}
                  className="text-sm text-app-cyan underline underline-offset-2 hover:text-white"
                >
                  View Interview Insights →
                </button>
              </div>
            </RevealOnScroll>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4 lg:sticky lg:top-[calc(var(--nav-height)+1.5rem)]">
          <RevealOnScroll delay={0.08}>
            <GlassPanel className="p-5">
              <p className="mb-3 text-xs uppercase tracking-[0.14em] text-app-muted">Why this matters</p>
              <p className="text-xs leading-5 text-app-muted">
                Without a brief, the insights layer has no frame of reference — it treats all themes as equally important.
                The brief tells the LLM which questions are load-bearing and which segment signals matter most.
              </p>
            </GlassPanel>
          </RevealOnScroll>

          <RevealOnScroll delay={0.1}>
            <GlassPanel className="p-5">
              <p className="mb-3 text-xs uppercase tracking-[0.14em] text-app-muted">Fit Tiers</p>
              <div className="space-y-1.5 text-xs text-app-muted">
                <p><span className="text-app-text">strong</span> — actively interested, researching solutions</p>
                <p><span className="text-app-text">soft</span> — recognizes need but has real concerns</p>
                <p><span className="text-app-text">latent</span> — has the need but hasn't considered a product solution</p>
                <p><span className="text-app-text">edge</span> — adjacent use case, conditional interest</p>
              </div>
            </GlassPanel>
          </RevealOnScroll>
        </div>
      </div>
    </SectionWrapper>
  );
}
