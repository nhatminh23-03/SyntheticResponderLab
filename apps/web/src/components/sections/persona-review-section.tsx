"use client";

import { useEffect, useState } from "react";

import { BadgeChip } from "@/components/ui/badge-chip";
import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import {
  PersonaSetPayload,
  finalizePersonaSet,
  generatePersonaPreview,
  getPersonaSet,
  savePersonaSetDraft,
} from "@/lib/api";
import {
  REQUIRED_SELECTION_COUNT,
  buildCandidateCsv,
  canFinalize,
  candidateCountText,
  selectionCounterText,
  setReviewerNote,
  toggleSelection,
} from "@/lib/persona-selection";
import { cn } from "@/lib/utils";
import { useStudy } from "@/providers/study-provider";

const CANDIDATE_COUNT = 15;

type CandidateRecord = Record<string, unknown>;

function fieldText(candidate: CandidateRecord, key: string): string {
  const value = candidate[key];
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "—";
  }
  return String(value);
}

function CandidateDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <div className="text-[0.6rem] uppercase tracking-[0.16em] text-app-muted">{label}</div>
      <div className="mt-1 text-sm leading-5 text-app-text">{value}</div>
    </div>
  );
}

function CandidateCard({
  candidate,
  isSelected,
  isLocked,
  note,
  onToggle,
  onNoteChange,
  onNoteBlur,
}: {
  candidate: CandidateRecord;
  isSelected: boolean;
  isLocked: boolean;
  note: string;
  onToggle: () => void;
  onNoteChange: (value: string) => void;
  onNoteBlur: () => void;
}) {
  const personaId = fieldText(candidate, "persona_id");
  return (
    <GlassPanel
      className={cn(
        "flex h-full flex-col p-4 transition duration-300",
        isSelected
          ? "[border-color:var(--color-border-strong)] [background:var(--color-brand-primary-soft)] [box-shadow:0_0_0_2px_var(--color-brand-primary)]"
          : "hover:[border-color:var(--color-border-strong)]"
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        disabled={isLocked}
        aria-pressed={isSelected}
        className={cn("w-full text-left", isLocked ? "cursor-default" : "cursor-pointer")}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-display text-lg tracking-[-0.02em] text-app-text">{personaId}</div>
            <div className="mt-1 text-xs text-app-muted">{fieldText(candidate, "segment_label")}</div>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <BadgeChip tone={isSelected ? "cyan" : "gold"}>
              {isSelected ? "Selected" : `Fit: ${fieldText(candidate, "fit_tier")}`}
            </BadgeChip>
            {isSelected ? (
              <span className="text-[0.62rem] uppercase tracking-[0.14em] text-app-cyan">
                Fit: {fieldText(candidate, "fit_tier")}
              </span>
            ) : null}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <CandidateDetail label="Age" value={fieldText(candidate, "age_bucket")} />
          <CandidateDetail label="Income" value={fieldText(candidate, "income_bucket")} />
          <CandidateDetail
            label="Housing"
            value={`${fieldText(candidate, "ownership")} · ${fieldText(candidate, "home_type")}`}
          />
          <CandidateDetail label="Household" value={fieldText(candidate, "household_size_bucket")} />
          <CandidateDetail label="Work Mode" value={fieldText(candidate, "work_mode")} />
          <CandidateDetail label="Awareness" value={fieldText(candidate, "awareness_stage")} />
        </div>

        <div className="mt-2 grid gap-2">
          <CandidateDetail label="Lifestyle" value={fieldText(candidate, "lifestyle_tags")} />
          <CandidateDetail label="Likely Use Case" value={fieldText(candidate, "likely_use_case")} />
          <CandidateDetail label="Likely Barrier" value={fieldText(candidate, "likely_barrier")} />
        </div>
      </button>

      {isSelected ? (
        <div className="mt-3">
          <label className="mb-1 block text-[0.6rem] uppercase tracking-[0.16em] text-app-muted">
            Reviewer note (optional)
          </label>
          <textarea
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            onBlur={onNoteBlur}
            disabled={isLocked}
            rows={2}
            placeholder="Why this persona belongs in the fixed set…"
            className="w-full resize-y rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-app-text placeholder-app-muted focus:border-app-cyan/30 focus:outline-none disabled:opacity-60"
          />
        </div>
      ) : null}
    </GlassPanel>
  );
}

export function PersonaReviewSection() {
  const { studyId, study } = useStudy();

  const [personaSet, setPersonaSet] = useState<PersonaSetPayload | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const isFinalized = personaSet?.status === "finalized";
  const candidates = personaSet?.candidates ?? [];

  function applyPersonaSet(payload: PersonaSetPayload | null) {
    setPersonaSet(payload);
    if (!payload) {
      setSelectedIds([]);
      setNotes({});
      return;
    }
    setSelectedIds(payload.selections.map((selection) => selection.candidate_id));
    const loadedNotes: Record<string, string> = {};
    for (const selection of payload.selections) {
      if (selection.reviewer_note) {
        loadedNotes[selection.candidate_id] = selection.reviewer_note;
      }
    }
    setNotes(loadedNotes);
  }

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      if (!studyId) {
        if (!cancelled) {
          applyPersonaSet(null);
          setStatusMsg(null);
          setErrorMsg(null);
        }
        return;
      }
      try {
        const payload = await getPersonaSet(studyId);
        if (cancelled) return;
        applyPersonaSet(payload);
        if (payload?.status === "finalized") {
          setStatusMsg("Fixed persona set loaded. Interviews will use these exact personas.");
        } else if (payload) {
          setStatusMsg("Draft selection loaded from the current study.");
        } else {
          setStatusMsg(null);
        }
        setErrorMsg(null);
      } catch (error) {
        if (cancelled) return;
        setErrorMsg(error instanceof Error ? error.message : "Persona set could not be loaded.");
      }
    }
    void hydrate();
    return () => {
      cancelled = true;
    };
  }, [studyId, study?.updated_at]);

  function buildSelectionsPayload(ids: string[]) {
    return ids.map((candidateId) => {
      const trimmed = (notes[candidateId] ?? "").trim();
      return trimmed
        ? { candidate_id: candidateId, reviewer_note: trimmed }
        : { candidate_id: candidateId };
    });
  }

  async function handleGenerate() {
    if (!studyId || isGenerating || isFinalized) return;
    setIsGenerating(true);
    setErrorMsg(null);
    setStatusMsg("Generating persona candidates with the grounded pipeline…");
    try {
      const { personaPreview } = await generatePersonaPreview(studyId, {
        sample_size: CANDIDATE_COUNT,
        use_grounded_priors: true,
        use_geography_filtered_priors: true,
        use_cex_affordability_priors: true,
      });
      if (!personaPreview?.preview_id) {
        throw new Error("Persona preview returned no batch id.");
      }
      // Pin the batch immediately: the fixed set references this run, so later previews
      // (e.g. the automatic one on experiment save) cannot silently swap the candidates.
      const pinned = await savePersonaSetDraft(studyId, {
        preview_run_id: personaPreview.preview_id,
        selections: [],
      });
      applyPersonaSet(pinned);
      setStatusMsg(
        `Candidate batch ${personaPreview.preview_id} generated (${personaPreview.generation_mode ?? "unknown mode"}).`
      );
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : "Candidate generation failed.");
      setStatusMsg(null);
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleSaveDraft() {
    if (!studyId || !personaSet || isFinalized) return;
    setIsSaving(true);
    setErrorMsg(null);
    try {
      const payload = await savePersonaSetDraft(studyId, {
        preview_run_id: personaSet.preview_run_id,
        selections: buildSelectionsPayload(selectedIds),
      });
      applyPersonaSet(payload);
      setStatusMsg("Draft selection saved.");
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : "Selection save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleFinalize() {
    if (!studyId || !personaSet || isFinalized || !canFinalize(selectedIds)) return;
    setIsSaving(true);
    setErrorMsg(null);
    try {
      await savePersonaSetDraft(studyId, {
        preview_run_id: personaSet.preview_run_id,
        selections: buildSelectionsPayload(selectedIds),
      });
      const payload = await finalizePersonaSet(studyId);
      applyPersonaSet(payload);
      setStatusMsg("Fixed persona set saved. Interviews will use these exact five personas.");
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : "Finalize failed.");
    } finally {
      setIsSaving(false);
    }
  }

  function handleExportCsv() {
    if (!personaSet) return;
    const csv = buildCandidateCsv({
      candidates,
      selectedIds,
      reviewerNotes: notes,
      generationMode: personaSet.generation_mode ?? null,
    });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `persona-candidates-${personaSet.preview_run_id}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <SectionWrapper id="persona-review" scrollable contentClassName="relative">
      <div className="min-w-0 space-y-6">
        <RevealOnScroll>
          <SectionHeader
            index={7}
            eyebrow="Personas"
            title="Review persona candidates and freeze the research set."
            description="Generate candidates with the grounded persona pipeline, review their research attributes, and select exactly five as the fixed set that later synthetic interviews reuse."
          />
        </RevealOnScroll>

        <RevealOnScroll delay={0.04}>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleGenerate}
              disabled={isGenerating || isFinalized || !studyId}
              className={cn(
                "inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-semibold tracking-[0.03em] transition",
                isGenerating || isFinalized || !studyId
                  ? "cursor-not-allowed opacity-50 border border-white/[0.08] bg-[rgba(17,24,29,0.88)] text-app-muted"
                  : "border border-app-cyan/40 bg-[linear-gradient(135deg,rgba(118,228,255,0.18),rgba(15,216,255,0.10))] text-app-text hover:-translate-y-0.5"
              )}
            >
              {isGenerating
                ? "Generating…"
                : candidates.length
                  ? "Regenerate candidates"
                  : `Generate ${CANDIDATE_COUNT} persona candidates`}
            </button>

            {candidates.length ? (
              <>
                <span className="rounded-full border border-app-cyan/25 bg-app-cyan/10 px-3 py-1 text-xs tracking-[0.08em] text-app-cyan">
                  {candidateCountText(candidates.length)}
                </span>
                <span
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs tracking-[0.08em]",
                    canFinalize(selectedIds)
                      ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-400"
                      : "border-white/[0.08] bg-white/[0.03] text-app-muted"
                  )}
                >
                  {selectionCounterText(selectedIds.length)}
                </span>
                {personaSet?.generation_mode ? (
                  <span className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1 text-xs tracking-[0.08em] text-app-muted">
                    Mode: {personaSet.generation_mode}
                  </span>
                ) : null}
                <span className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1 text-xs tracking-[0.08em] text-app-muted">
                  Batch: {personaSet?.preview_run_id}
                </span>
              </>
            ) : null}
          </div>
        </RevealOnScroll>

        {isFinalized ? (
          <RevealOnScroll delay={0.05}>
            <div className="rounded-2xl border border-emerald-400/25 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-300">
              Fixed persona set {personaSet?.set_id} is finalized
              {personaSet?.finalized_at ? ` (${personaSet.finalized_at})` : ""}. Later interviews
              use these exact five personas — selection is locked.
            </div>
          </RevealOnScroll>
        ) : null}

        {errorMsg ? <p className="text-sm text-red-400">{errorMsg}</p> : null}
        {!errorMsg && statusMsg ? <p className="text-sm text-app-muted">{statusMsg}</p> : null}

        {candidates.length ? (
          <RevealOnScroll delay={0.06}>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {candidates.map((candidate) => {
                const candidateId = String(candidate.candidate_id ?? "");
                return (
                  <CandidateCard
                    key={candidateId}
                    candidate={candidate}
                    isSelected={selectedIds.includes(candidateId)}
                    isLocked={isFinalized}
                    note={notes[candidateId] ?? ""}
                    onToggle={() => {
                      if (isFinalized) return;
                      setSelectedIds((prev) => toggleSelection(prev, candidateId));
                    }}
                    onNoteChange={(value) =>
                      setNotes((prev) => ({ ...prev, [candidateId]: value }))
                    }
                    onNoteBlur={() =>
                      setNotes((prev) => setReviewerNote(prev, candidateId, prev[candidateId] ?? ""))
                    }
                  />
                );
              })}
            </div>
          </RevealOnScroll>
        ) : (
          <RevealOnScroll delay={0.06}>
            <GlassPanel className="p-6 text-sm text-app-muted">
              No candidate batch yet. Save Audience and the Experiment plan first, then generate
              {" "}{CANDIDATE_COUNT} candidates here for review.
            </GlassPanel>
          </RevealOnScroll>
        )}

        {candidates.length ? (
          <RevealOnScroll delay={0.08}>
            <div className="flex flex-wrap items-center gap-3">
              {!isFinalized ? (
                <>
                  <button
                    type="button"
                    onClick={handleSaveDraft}
                    disabled={isSaving}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm transition",
                      isSaving
                        ? "cursor-not-allowed opacity-50 border-white/[0.08] text-app-muted"
                        : "border-white/[0.12] text-app-text hover:-translate-y-0.5"
                    )}
                  >
                    {isSaving ? "Saving…" : "Save draft selection"}
                  </button>
                  <button
                    type="button"
                    onClick={handleFinalize}
                    disabled={isSaving || !canFinalize(selectedIds)}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-semibold tracking-[0.03em] transition",
                      isSaving || !canFinalize(selectedIds)
                        ? "cursor-not-allowed opacity-50 border border-white/[0.08] bg-[rgba(17,24,29,0.88)] text-app-muted"
                        : "border border-app-cyan/40 bg-[linear-gradient(135deg,rgba(118,228,255,0.18),rgba(15,216,255,0.10))] text-app-text hover:-translate-y-0.5"
                    )}
                  >
                    Save Fixed Persona Set
                  </button>
                  {!canFinalize(selectedIds) ? (
                    <span className="text-xs text-app-muted">
                      Select exactly {REQUIRED_SELECTION_COUNT} personas to finalize.
                    </span>
                  ) : null}
                </>
              ) : null}
              <button
                type="button"
                onClick={handleExportCsv}
                className="inline-flex items-center gap-2 rounded-full border border-white/[0.12] px-5 py-2.5 text-sm text-app-text transition hover:-translate-y-0.5"
              >
                Export CSV
              </button>
            </div>
          </RevealOnScroll>
        ) : null}
      </div>
    </SectionWrapper>
  );
}
