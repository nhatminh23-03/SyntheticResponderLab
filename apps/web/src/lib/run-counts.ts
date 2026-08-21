/**
 * Names the three quantities a run produces, so none of them can be mistaken for another.
 *
 * A mirror run of N personas across M models performs N x M surveys and stores N x M x questions
 * answer rows. The Result tile used to count distinct respondent ids, which mirror mode deliberately
 * reuses across models, so a 20-persona two-model run displayed "20" for 40 completed surveys and
 * 1,280 stored answers.
 */

export type RunCountsInput =
  | {
      run_counts?: {
        personas?: number;
        executions?: number;
        questions?: number;
        answer_records?: number;
      } | null;
      response_records?: Array<{ respondent_id?: unknown; model?: unknown }> | null;
      response_record_preview?: Array<{ respondent_id?: unknown; model?: unknown }> | null;
      question_count?: number | null;
    }
  | null
  | undefined;

export type RunCounts = {
  available: boolean;
  /** True when the numbers were derived from a preview sample rather than the full record set. */
  isPartial: boolean;
  personas: number;
  executions: number;
  questions: number;
  answerRecords: number;
  responsesLabel: string;
  responsesValue: string;
  detail: string;
};

const EMPTY: RunCounts = {
  available: false,
  isPartial: false,
  personas: 0,
  executions: 0,
  questions: 0,
  answerRecords: 0,
  responsesLabel: "Responses",
  responsesValue: "—",
  detail: "No run has been saved yet.",
};

function toCount(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) && parsed > 0 ? Math.trunc(parsed) : 0;
}

function plural(count: number, noun: string): string {
  return `${count.toLocaleString("en-US")} ${noun}${count === 1 ? "" : "s"}`;
}

export function describeRunCounts(result: RunCountsInput): RunCounts {
  if (!result) {
    return EMPTY;
  }

  const saved = result.run_counts;
  if (saved && toCount(saved.executions) > 0) {
    const personas = toCount(saved.personas);
    const executions = toCount(saved.executions);
    const answerRecords = toCount(saved.answer_records);
    return {
      available: true,
      isPartial: false,
      personas,
      executions,
      questions: toCount(saved.questions),
      answerRecords,
      responsesLabel: "Responses",
      responsesValue: executions.toLocaleString("en-US"),
      detail: `${plural(personas, "persona")} · ${plural(executions, "completed survey")} · ${plural(
        answerRecords,
        "answer"
      )}`,
    };
  }

  // Runs saved before the counts were recorded still have their rows; deriving is better than
  // showing a confident zero.
  const full = result.response_records ?? [];
  const rows = full.length > 0 ? full : result.response_record_preview ?? [];
  if (rows.length === 0) {
    return EMPTY;
  }

  const personaIds = new Set<string>();
  const executionKeys = new Set<string>();
  for (const row of rows) {
    const respondent = row?.respondent_id == null ? "" : String(row.respondent_id);
    if (!respondent) {
      continue;
    }
    personaIds.add(respondent);
    executionKeys.add(`${respondent}::${row?.model == null ? "" : String(row.model)}`);
  }

  const personas = personaIds.size;
  const executions = executionKeys.size;
  const answerRecords = rows.length;
  const isPartial = full.length === 0;

  return {
    available: true,
    isPartial,
    personas,
    executions,
    questions: toCount(result.question_count),
    answerRecords,
    responsesLabel: "Responses",
    responsesValue: executions.toLocaleString("en-US"),
    detail: isPartial
      ? `${plural(personas, "persona")} · ${plural(executions, "completed survey")} · from a preview sample`
      : `${plural(personas, "persona")} · ${plural(executions, "completed survey")} · ${plural(
          answerRecords,
          "answer"
        )}`,
  };
}
