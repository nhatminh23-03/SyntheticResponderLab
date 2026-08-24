/**
 * Pure helpers for the persona candidate review flow: 15 grounded candidates,
 * exactly 5 selected, selection state and reviewer notes exported as CSV.
 *
 * The CSV columns are a strict whitelist so persona fields outside the research
 * attributes (and anything internal) can never leak into an export.
 */

export const REQUIRED_SELECTION_COUNT = 5;

export type CandidateRecord = Record<string, unknown>;

const CSV_PERSONA_COLUMNS = [
  "persona_id",
  "segment_label",
  "fit_tier",
  "age_bucket",
  "income_bucket",
  "ownership",
  "home_type",
  "household_size_bucket",
  "work_mode",
  "likely_use_case",
  "likely_barrier",
  "awareness_stage",
] as const;

const CSV_HEADER = [...CSV_PERSONA_COLUMNS, "generation_mode", "review_status", "reviewer_notes"];

export function toggleSelection(
  selected: string[],
  candidateId: string,
  limit: number = REQUIRED_SELECTION_COUNT,
): string[] {
  if (selected.includes(candidateId)) {
    return selected.filter((id) => id !== candidateId);
  }
  if (selected.length >= limit) {
    return selected;
  }
  return [...selected, candidateId];
}

export function canFinalize(selected: string[]): boolean {
  return selected.length === REQUIRED_SELECTION_COUNT;
}

export function selectionCounterText(selectedCount: number): string {
  return `Selected ${selectedCount} / ${REQUIRED_SELECTION_COUNT}`;
}

export function candidateCountText(count: number): string {
  return `${count} candidates generated`;
}

export function setReviewerNote(
  notes: Record<string, string>,
  candidateId: string,
  note: string,
): Record<string, string> {
  const next = { ...notes };
  const trimmed = note.trim();
  if (trimmed) {
    next[candidateId] = trimmed;
  } else {
    delete next[candidateId];
  }
  return next;
}

function escapeCsvField(value: string): string {
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function buildCandidateCsv(args: {
  candidates: CandidateRecord[];
  selectedIds: string[];
  reviewerNotes: Record<string, string>;
  generationMode: string | null;
}): string {
  const { candidates, selectedIds, reviewerNotes, generationMode } = args;
  const selected = new Set(selectedIds);

  const rows = candidates.map((candidate) => {
    const candidateId = String(candidate.candidate_id ?? "");
    const personaCells = CSV_PERSONA_COLUMNS.map((column) => {
      const value = candidate[column];
      return value === null || value === undefined ? "" : String(value);
    });
    return [
      ...personaCells,
      generationMode ?? "",
      selected.has(candidateId) ? "selected" : "not_selected",
      reviewerNotes[candidateId] ?? "",
    ]
      .map(escapeCsvField)
      .join(",");
  });

  return [CSV_HEADER.join(","), ...rows].join("\r\n");
}
