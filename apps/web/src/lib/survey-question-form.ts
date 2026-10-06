export type AddedQuestionType = "likert" | "single_choice";
export type AddedQuestionDraft = { text: string; questionType: AddedQuestionType; options: string[] };
export const DEFAULT_LIKERT_ANCHORS = ["Not at all interested", "Slightly interested", "Moderately interested", "Very interested", "Extremely interested"];

const squash = (text: string) => text.split(/\s+/).filter(Boolean).join(" ");

export function toAddQuestionPayload(draft: AddedQuestionDraft) {
  return { text: squash(draft.text), question_type: draft.questionType, options: draft.options.map((o) => o.trim()).filter(Boolean) };
}

export function validateAddedQuestion(draft: AddedQuestionDraft): string | null {
  const payload = toAddQuestionPayload(draft);
  if (payload.text.length < 5 || payload.text.length > 300) return "Question text must be at least 5 characters (and at most 300).";
  if (draft.questionType === "likert" && payload.options.length !== 5) return "A 1–5 scale needs five labels, one per point.";
  if (draft.questionType === "single_choice") {
    const unique = new Set(payload.options);
    if (payload.options.length < 2 || payload.options.length > 8 || unique.size !== payload.options.length) {
      return "A single-choice question needs 2 to 8 different options.";
    }
  }
  return null;
}

export const isStudentQuestion = (id: string) => /^SQ\d+$/.test(id);
