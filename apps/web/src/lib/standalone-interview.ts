export type Batch = {
  job_id: string;
  status: "running" | "completed" | "failed" | "budget_stopped";
  revision: number;
  persona_count: number;
  completed_personas: number;
  interviewer_model: string;
  interviewee_model: string;
  turn_limit: number;
  estimated_cost_usd: string;
  session_usage: { cost_usd: string };
  transcripts: { persona_id: string; messages: { role: "user" | "assistant"; content: string }[] }[];
  error: { code: string; message: string; details?: { scope?: string } } | null;
};

export async function interviewOperation<T>(studyId: string, path: string, payload?: object): Promise<T> {
  const response = await fetch(`/api/backend/api/v1/studies/${encodeURIComponent(studyId)}/interview/${path}`, {
    method: payload ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    ...(payload ? { body: JSON.stringify(payload) } : {}),
  });
  const result = await response.json();
  if (!response.ok) {
    if (result.error?.code === "quota_exceeded" && result.error?.details?.batch) {
      return { batch: result.error.details.batch } as T;
    }
    throw new Error(result.error?.message || `Interview request failed (${response.status}).`);
  }
  return result.data as T;
}

export type RegeneratedAnswer = {
  answer_id: string;
  version: number;
  reply: string;
  session_usage: { cost_usd: string };
  budget_stop?: { message: string } | null;
  post_interview_score: { fit_tier: "strong" | "soft" | "latent" | "edge"; emotional_classification: "positive" | "neutral" | "negative" };
};
