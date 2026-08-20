/**
 * Describes how an interview batch was actually produced.
 *
 * Neo mode short-circuits to a seeded demo fixture: no interview model is called, "Model B" is
 * Model A's text plus a fixed clause, and the grounding score is a lookup on persona fit tier
 * rather than a judge model. The interview UI must not claim dual-model verification for that.
 */
export type InterviewProvenanceInput = {
  demo_fixture?: boolean | null;
  fixture_source?: string | null;
  judge_model?: string | null;
  model_a?: string | null;
  model_b?: string | null;
} | null;

export type InterviewProvenance = {
  isFixture: boolean;
  claimsDualModel: boolean;
  claimsJudgeModel: boolean;
  headline: string;
  detail: string;
  /** Non-null when the displayed grounding score is not a real inter-model agreement measure. */
  groundingScoreCaveat: string | null;
};

export function describeInterviewProvenance(
  run: InterviewProvenanceInput
): InterviewProvenance {
  if (!run) {
    return {
      isFixture: false,
      claimsDualModel: false,
      claimsJudgeModel: false,
      headline: "No interview run yet",
      detail: "Run the interviews to see how this batch was produced.",
      groundingScoreCaveat: null,
    };
  }

  if (run.demo_fixture) {
    return {
      isFixture: true,
      claimsDualModel: false,
      claimsJudgeModel: false,
      headline: "Seeded demo data — not a live interview run",
      detail:
        "No model was called for these transcripts. They are generated fixture text for the " +
        "guided demo, the second transcript is a variation of the first, and the grounding " +
        "score is derived from persona fit tier rather than a judge model. The model names " +
        "shown are placeholders. Use a Custom Study for a genuine dual-model interview batch.",
      groundingScoreCaveat:
        "Derived from persona fit tier — this is not a measure of agreement between models.",
    };
  }

  const judge = run.judge_model?.trim();
  const models = [run.model_a, run.model_b].filter(Boolean).join(" and ");
  return {
    isFixture: false,
    claimsDualModel: true,
    claimsJudgeModel: Boolean(judge),
    headline: "Live interview run",
    detail: models
      ? `${models} each answered the guide independently${judge ? `, and ${judge} scored agreement across four dimensions` : ""}.`
      : `Interviews were generated live${judge ? ` and scored by ${judge}` : ""}.`,
    groundingScoreCaveat: null,
  };
}
