/**
 * Describes which answers a chart is actually built from.
 *
 * Fabricated answers stay in the saved dataset with provenance, but are excluded from charts, means
 * and rankings. A reader needs to see that exclusion, not just be left with a smaller number.
 */
export type AnswerSourcingPayload = {
  live_answers_used?: number;
  fallback_answers_excluded?: number;
  total_answers?: number;
  live_answer_rate?: number | null;
} | null;

export type FormattedAnswerSourcing = {
  shown: boolean;
  liveAnswers: number;
  excluded: number;
  totalAnswers: number;
  ratePercent: number | null;
  summary: string;
};

export function formatAnswerSourcing(payload: AnswerSourcingPayload): FormattedAnswerSourcing {
  if (!payload) {
    return {
      shown: false,
      liveAnswers: 0,
      excluded: 0,
      totalAnswers: 0,
      ratePercent: null,
      summary: "",
    };
  }

  const liveAnswers = payload.live_answers_used ?? 0;
  const excluded = payload.fallback_answers_excluded ?? 0;
  const totalAnswers = payload.total_answers ?? liveAnswers + excluded;
  const rate = payload.live_answer_rate;
  const ratePercent = typeof rate === "number" ? Math.round(rate * 1000) / 10 : null;

  let summary: string;
  if (excluded === 0) {
    summary = `All ${liveAnswers} answers came from a live model.`;
  } else if (liveAnswers === 0) {
    // "Built from 0 live answers" describes a construction that did not happen. Nothing was built,
    // and that is the thing the reader needs to know.
    summary = `No live model answers were returned. All ${totalAnswers} ${
      totalAnswers === 1 ? "answer is" : "answers are"
    } deterministic filler and remain in the saved records, flagged.`;
  } else {
    summary = `Built from ${liveAnswers} live answers. ${excluded} fabricated ${
      excluded === 1 ? "answer was" : "answers were"
    } excluded — they remain in the saved records, flagged.`;
  }

  return { shown: true, liveAnswers, excluded, totalAnswers, ratePercent, summary };
}
