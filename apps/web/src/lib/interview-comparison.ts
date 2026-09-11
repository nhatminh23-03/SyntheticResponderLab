import type { InterviewModelCatalogEntry } from "./api";


export const MIN_INTERVIEW_COMPARISON_MODELS = 2;
export const POST_INTERVIEW_SCORE_LABEL = "scored after the interview, never before";

export type InterviewPostScore = {
  fitTier: "strong" | "soft" | "latent" | "edge";
  emotionalClassification: "positive" | "neutral" | "negative";
};

export type InterviewComparisonResult = {
  answerId?: string;
  version?: number;
  modelId: string;
  answer: string | null;
  error: string | null;
  postInterviewScore: InterviewPostScore | null;
  // A budget stop can arrive with every model already answered. The per-card `error`
  // only shows on a card that has no answer, so the stop would vanish exactly when
  // the student spent the most. Carried here so the page can show it regardless.
  budgetStop?: string;
};

type InterviewComparisonResponse = {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
};

type InterviewComparisonFetch = (
  input: string,
  init: RequestInit
) => Promise<InterviewComparisonResponse>;

type InterviewComparisonInput = {
  studyId: string;
  personaId: string;
  question: string;
  modelIds: string[];
  allowExpensiveModels: boolean;
};

export function defaultInterviewComparisonModelIds(
  models: InterviewModelCatalogEntry[]
) {
  return models
    .filter((model) => model.tier !== "expensive")
    .slice(0, MIN_INTERVIEW_COMPARISON_MODELS)
    .map((model) => model.id);
}

export function toggleInterviewComparisonModel(
  selectedModelIds: string[],
  modelId: string,
  selected: boolean
) {
  if (selected) {
    return selectedModelIds.includes(modelId)
      ? selectedModelIds
      : [...selectedModelIds, modelId];
  }
  return selectedModelIds.filter((selectedId) => selectedId !== modelId);
}

export function removeExpensiveComparisonModels(
  models: InterviewModelCatalogEntry[],
  selectedModelIds: string[]
) {
  const expensiveIds = new Set(
    models.filter((model) => model.tier === "expensive").map((model) => model.id)
  );
  return selectedModelIds.filter((modelId) => !expensiveIds.has(modelId));
}

export function canRunInterviewComparison(selectedModelIds: string[]) {
  return new Set(selectedModelIds).size >= MIN_INTERVIEW_COMPARISON_MODELS;
}

export function orderInterviewComparisonModelIds(
  models: InterviewModelCatalogEntry[],
  selectedModelIds: string[]
) {
  const selectedIds = new Set(selectedModelIds);
  return models.filter((model) => selectedIds.has(model.id)).map((model) => model.id);
}

export async function runInterviewComparison(
  input: InterviewComparisonInput,
  fetcher: InterviewComparisonFetch = fetch
): Promise<InterviewComparisonResult[]> {
  try {
    const response = await fetcher(
      `/api/backend/api/v1/studies/${encodeURIComponent(input.studyId)}/interview/compare`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          persona_id: input.personaId,
          question: input.question,
          model_ids: input.modelIds,
          allow_expensive_models: input.allowExpensiveModels,
        }),
      }
    );
    const payload = (await response.json()) as {
      data?: {
        interview_comparison?: {
          results?: Array<{
            model_id?: unknown;
            answer_id?: string;
            version?: number;
            answer?: unknown;
            error?: unknown;
            post_interview_score?: {
              fit_tier?: unknown;
              emotional_classification?: unknown;
              label?: unknown;
            };
          }>;
        };
      };
      error?: unknown;
    };

    let rawResults = payload.data?.interview_comparison?.results;
    let failureMessage: string | null = null;
    if (!response.ok) {
      const apiError = payload.error;
      const message =
        typeof apiError === "string"
          ? apiError
          : apiError && typeof apiError === "object" && "message" in apiError
            ? String(apiError.message)
            : `Model comparison failed (${response.status}).`;
      failureMessage = message;
      // A quota stop can include answers committed before the cap was reached.
      const details = apiError && typeof apiError === "object" &&
        "code" in apiError && apiError.code === "quota_exceeded" &&
        "details" in apiError ? apiError.details : null;
      rawResults = details && typeof details === "object" &&
        "results" in details && Array.isArray(details.results)
        ? details.results : [];
    }

    if (!Array.isArray(rawResults)) {
      throw new Error("Model comparison returned an invalid response.");
    }
    const byModelId = new Map(rawResults.map((result) => [result.model_id, result]));
    return input.modelIds.map((modelId) => {
      const result = byModelId.get(modelId);
      const answer = typeof result?.answer === "string" ? result.answer.trim() : "";
      const error = typeof result?.error === "string" ? result.error : null;
      const rawScore = result?.post_interview_score;
      const fitTier = rawScore?.fit_tier;
      const emotionalClassification = rawScore?.emotional_classification;
      const scoreIsValid =
        rawScore?.label === POST_INTERVIEW_SCORE_LABEL &&
        ["strong", "soft", "latent", "edge"].includes(String(fitTier)) &&
        ["positive", "neutral", "negative"].includes(String(emotionalClassification));
      return {
        modelId,
        ...(result?.answer_id ? { answerId: result.answer_id, version: result.version ?? 0 } : {}),
        ...(failureMessage ? { budgetStop: failureMessage } : {}),
        answer: answer || null,
        error: answer ? null : error ?? failureMessage ?? "Model returned an empty answer.",
        postInterviewScore: answer && scoreIsValid
          ? {
              fitTier: fitTier as InterviewPostScore["fitTier"],
              emotionalClassification:
                emotionalClassification as InterviewPostScore["emotionalClassification"],
            }
          : null,
      };
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Model comparison request failed.";
    return input.modelIds.map((modelId) => ({
      modelId,
      answer: null,
      error: message,
      postInterviewScore: null,
    }));
  }
}
