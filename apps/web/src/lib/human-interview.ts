import { batchExport } from "./interview-batch-export";
import { InterviewOperationError, interviewOperation, type Batch } from "./standalone-interview";

/** How the student reads in an export: the persona column of the batch file. */
export const HUMAN_RESPONDENT_LABEL = "Human respondent (student)";
export const HUMAN_INTERVIEWEE_MODEL = "none - a human answered";

/** The interviewer agent's roles: "user" is the AI's question, "assistant" the student's answer. */
export type HumanMessage = { role: "user" | "assistant"; content: string };

export type HumanQuestion = {
  session_id: string;
  question: string | null;
  complete: boolean;
  turn_number: number;
  turn_limit: number;
  interviewer_model: string;
  session_usage: { cost_usd: string };
};

export type HumanInterview = {
  demo?: boolean;
  provisional?: boolean;
  sessionId: string | null;
  messages: HumanMessage[];
  ended: boolean;
  model: string;
  turnLimit: number;
  costUsd: string;
};

export const NEW_HUMAN_INTERVIEW: HumanInterview = {
  sessionId: null, messages: [], ended: false, model: "", turnLimit: 8, costUsd: "0",
};

/** The student's answers leave the browser here and nowhere else. */
export async function nextHumanQuestion(studyId: string, sessionId: string | null, messages: HumanMessage[]) {
  return (await interviewOperation<{ question: HumanQuestion }>(studyId, "human/next-question",
    { session_id: sessionId, messages })).question;
}

/** Only an answer to the question on screen, one at a time, while the interview is open. */
export function canSendAnswer(interview: HumanInterview, answer: string, pending: boolean) {
  return !interview.ended && !pending && answer.trim() !== ""
    && interview.messages.at(-1)?.role === "user";
}

/** Fold the server's reply in. A reply that lands after End is dropped: the student stopped. */
export function withQuestion(interview: HumanInterview, answered: HumanMessage[], reply: HumanQuestion): HumanInterview {
  if (interview.ended) return interview;
  return {
    sessionId: reply.session_id,
    messages: reply.question ? [...answered, { role: "user", content: reply.question }] : answered,
    ended: reply.complete,
    model: reply.interviewer_model,
    turnLimit: reply.turn_limit,
    costUsd: reply.session_usage.cost_usd,
  };
}

/** Worth a leave warning: nothing is stored, so a refresh loses it. */
export function isUnfinished(interview: HumanInterview) {
  return interview.messages.length > 0 && !interview.ended;
}

/** What the student is told, and whether the interview is over. The typed answer is never cleared here. */
export function describeFailure(error: unknown): { message: string; ends: boolean } {
  if (error instanceof InterviewOperationError) {
    if (error.status === 429) return { message: `${error.message} The interview has ended; you can still export it.`, ends: true };
    return { message: error.message, ends: false };
  }
  // fetch rejects, or a proxy error page is not JSON.
  return { message: "Could not reach the server. Your answer is kept; send it again to retry.", ends: false };
}

/** The same single file a batch exports, with the respondent named as a human on every row. */
export function humanInterviewExport(interview: HumanInterview, format: "csv" | "md") {
  const batch: Batch = {
    demo: interview.demo,
    provisional: interview.provisional,
    job_id: interview.sessionId ?? "ai-interviews-you",
    status: "completed",
    revision: 0,
    persona_count: 1,
    completed_personas: 1,
    interviewer_model: interview.model,
    interviewee_model: HUMAN_INTERVIEWEE_MODEL,
    turn_limit: interview.turnLimit,
    estimated_cost_usd: "0",
    session_usage: { cost_usd: interview.costUsd },
    transcripts: [{ persona_id: HUMAN_RESPONDENT_LABEL, messages: interview.messages }],
    error: null,
  };
  return batchExport(batch, format);
}
