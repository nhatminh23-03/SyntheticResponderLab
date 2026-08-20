/**
 * Turns a run's saved diagnostics into something a reader can act on.
 *
 * The backend has always computed and shipped these numbers — live answer rate, fallback count,
 * provider errors, malformed JSON, persona generation mode — but no component read them, so a run
 * whose answers were partly or wholly deterministic filler looked identical to a genuine one.
 */

export type RunDebugSummaryInput = {
  total_answers?: number;
  truly_live_answers?: number;
  fallback_answers?: number;
  provider_error_count?: number;
  malformed_json_count?: number;
  live_answer_rate?: number | null;
} | null;

export type RunEvidenceTone = "ok" | "caution" | "critical" | "unknown";

export type RunEvidence = {
  available: boolean;
  tone: RunEvidenceTone;
  liveAnswerRatePercent: number | null;
  liveAnswerRateLabel: string;
  totalAnswers: number;
  liveAnswers: number;
  fabricatedAnswers: number;
  providerErrors: number;
  malformedJson: number;
  headline: string;
  detail: string;
  personaGrounding: { isGrounded: boolean; label: string; detail: string };
};

const GROUNDED_MODES = new Set(["grounded_priors", "grounded"]);

function describePersonaGrounding(mode: string | null | undefined) {
  if (!mode) {
    return {
      isGrounded: false,
      label: "Persona sourcing not reported",
      detail: "This run did not record how its personas were generated.",
    };
  }
  if (GROUNDED_MODES.has(mode)) {
    return {
      isGrounded: true,
      label: "Grounded personas",
      detail: "Personas were sampled from installed prior tables.",
    };
  }
  return {
    isGrounded: false,
    label: "Rule-based personas (not grounded)",
    detail:
      "Grounding priors were unavailable, so personas came from deterministic heuristics. " +
      "Do not describe them as a census-grounded or representative sample.",
  };
}

export function describeRunEvidence(
  summary: RunDebugSummaryInput,
  personaGenerationMode: string | null | undefined
): RunEvidence {
  const personaGrounding = describePersonaGrounding(personaGenerationMode);

  if (!summary) {
    return {
      available: false,
      tone: "unknown",
      liveAnswerRatePercent: null,
      liveAnswerRateLabel: "Not reported",
      totalAnswers: 0,
      liveAnswers: 0,
      fabricatedAnswers: 0,
      providerErrors: 0,
      malformedJson: 0,
      headline: "Answer sourcing not reported",
      detail: "This run saved no diagnostics, so how much of it came from a live model is unknown.",
      personaGrounding,
    };
  }

  const totalAnswers = summary.total_answers ?? 0;
  const liveAnswers = summary.truly_live_answers ?? 0;
  const fabricatedAnswers = summary.fallback_answers ?? 0;
  const providerErrors = summary.provider_error_count ?? 0;
  const malformedJson = summary.malformed_json_count ?? 0;

  const rawRate = summary.live_answer_rate;
  const ratePercent =
    typeof rawRate === "number" ? Math.round(rawRate * 1000) / 10 : null;

  let tone: RunEvidenceTone = "unknown";
  let headline = "Answer sourcing not reported";
  let detail = "This run saved no live-answer rate.";

  if (ratePercent !== null) {
    if (ratePercent >= 100) {
      tone = "ok";
      headline = "All answers came from a live model";
      detail = `${liveAnswers} of ${totalAnswers} answers were returned by the selected models.`;
    } else if (ratePercent <= 0) {
      tone = "critical";
      headline = "No live answers — every value was fabricated";
      detail =
        `All ${totalAnswers} answers are deterministic filler generated to keep the record set ` +
        "complete. Do not read this run as evidence.";
    } else {
      tone = "caution";
      headline = "Some answers were fabricated";
      detail =
        `${fabricatedAnswers} of ${totalAnswers} answers could not be used from the model and were ` +
        "replaced with deterministic filler. They are stored under the real model name, so charts " +
        "include them.";
    }
  }

  return {
    available: true,
    tone,
    liveAnswerRatePercent: ratePercent,
    liveAnswerRateLabel: ratePercent === null ? "Not reported" : `${ratePercent}% live`,
    totalAnswers,
    liveAnswers,
    fabricatedAnswers,
    providerErrors,
    malformedJson,
    headline,
    detail,
    personaGrounding,
  };
}
