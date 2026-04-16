const DEFAULT_API_BASE_URL = "http://localhost:8000";

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? DEFAULT_API_BASE_URL;
}

type ApiErrorResponse = {
  error?: {
    message?: string;
  };
};

async function readApiErrorMessage(response: Response, fallback: string) {
  const body = await response.text();
  if (!body) {
    return fallback;
  }

  try {
    const payload = JSON.parse(body) as ApiErrorResponse;
    return payload.error?.message || body;
  } catch {
    return body;
  }
}

export type CreateStudyResponse = {
  data?: {
    study?: {
      study_id?: string;
    };
  };
};

export type AudiencePayload = {
  state?: string | null;
  metro?: string | null;
  zip_code?: string | null;
  age_min?: number | null;
  age_max?: number | null;
  income_min?: number | null;
  income_max?: number | null;
  homeowner_only?: boolean;
  renter_only?: boolean;
  household_size_min?: number | null;
  household_size_max?: number | null;
  work_from_home?: boolean | null;
  lifestyle_tags?: string[];
  home_type?: string | null;
  notes?: string | null;
};

export type ProductPayload = {
  business_name?: string | null;
  industry?: string | null;
  product_name?: string | null;
  product_type?: string | null;
  product_description?: string | null;
  target_customer?: string | null;
  price_range?: string | null;
  primary_goal?: string | null;
  key_features?: string[];
  main_use_cases?: string[];
  main_pain_points_solved?: string[];
  main_barriers_or_concerns?: string[];
  product_image_labels?: string[];
  product_image_objects?: string[];
  product_image_colors?: string[];
  notes?: string | null;
};

export type MarketCompetitorPayload = {
  name?: string | null;
  product_type?: string | null;
  price_range?: string | null;
  key_features?: string[];
  strengths?: string[];
  weaknesses?: string[];
};

export type MarketPayload = {
  category?: string | null;
  direct_competitors?: MarketCompetitorPayload[];
  substitutes?: string[];
  typical_price_band?: string | null;
  common_expected_features?: string[];
  common_objections?: string[];
  notes?: string | null;
};

export type ExperimentPayload = {
  sample_size?: number;
  selected_models?: string[];
  experiment_mode?: "split" | "mirror" | "stability";
  reruns_per_persona?: number;
  mirror_personas_across_models?: boolean;
  split_across_models?: boolean;
  notes?: string | null;
};

export type SurveyQuestionPayload = {
  id: string;
  text: string;
  question_type:
    | "single_choice"
    | "multi_choice"
    | "likert"
    | "numeric"
    | "open_text";
  options?: string[];
  required?: boolean;
  min_value?: number | null;
  max_value?: number | null;
  help_text?: string | null;
};

export type SurveySchemaPayload = {
  survey_title?: string | null;
  description?: string | null;
  source_format?: string | null;
  parse_warnings?: string[];
  questions?: SurveyQuestionPayload[];
};

export type SurveyApiState = {
  status?: string;
  source_asset_id?: string | null;
  source_filename?: string | null;
  source_format?: string | null;
  schema?: SurveySchemaPayload | null;
  schema_?: SurveySchemaPayload | null;
  question_count?: number | null;
  parse_warnings?: string[];
  saved_at?: string | null;
  updated_at?: string | null;
};

export type WorkflowReadiness = {
  ready_for_persona_preview?: boolean;
  stages?: Array<{
    stage_key: string;
    status: string;
    hard_blockers?: string[];
    warnings?: string[];
    missing_fields?: string[];
  }>;
};

export type ProductEnrichmentSummary = {
  enrichment_id: string;
  status: string;
  input_url?: string | null;
  source_asset_id?: string | null;
  scraped_text_asset_id?: string | null;
  analysis?: Record<string, unknown> | null;
  proposed_product_patch?: ProductPayload | null;
  warnings?: string[];
  error?: Record<string, unknown> | null;
  applied_to_product?: boolean;
  created_at?: string;
  completed_at?: string | null;
};

export type ModelCatalogEntry = {
  id: string;
  name?: string;
  prompt_price_per_million?: number | null;
  completion_price_per_million?: number | null;
};

export type PersonaPreviewRequest = {
  sample_size?: number;
  use_grounded_priors?: boolean;
  use_geography_filtered_priors?: boolean;
  use_cex_affordability_priors?: boolean;
  seed?: number | null;
};

export type PersonaPreviewPayload = {
  preview_id: string;
  status: string;
  request: PersonaPreviewRequest;
  generation_mode?: string | null;
  grounded_priors_available?: boolean | null;
  cex_affordability_available?: boolean | null;
  geography_context?: Record<string, unknown> | null;
  prior_notes?: Array<Record<string, unknown>>;
  warning_messages?: string[];
  personas?: Array<Record<string, unknown>>;
  created_at?: string;
  completed_at?: string | null;
};

export type PromptPreviewPayload = {
  persona_index: number;
  persona_id?: string | null;
  persona_label?: string | null;
  survey_title?: string | null;
  system_instruction: string;
  user_instruction: string;
  combined_prompt: string;
};

export type SimulationRunConditions = {
  context_influence?: {
    enabled?: boolean;
    sources?: string[];
  };
  geography_aware_priors?: {
    status?: string;
    detail?: string;
  };
  grounded_priors?: {
    status?: string;
    detail?: string;
  };
  affordability_priors?: {
    status?: string;
    detail?: string;
  };
  generation_mode?: string;
  selected_models?: string[];
};

export type SimulationRunDebugSummary = {
  primary_live_path?: boolean;
  total_answers?: number;
  truly_live_answers?: number;
  fallback_answers?: number;
  provider_error_count?: number;
  malformed_json_count?: number;
  live_answer_rate?: number | null;
  ml_persona_completion_enabled?: boolean;
};

export type SimulationRunResultPayload = {
  run_id: string;
  status: string;
  total_requested_responses: number;
  total_generated_responses: number;
  models_used: string[];
  experiment_mode: string;
  survey_title?: string | null;
  question_count?: number | null;
  notes?: string | null;
  created_at?: string | null;
  generation_mode?: string | null;
  provider_model_name?: string | null;
  persona_generation_mode?: string | null;
  grounded_priors_available?: boolean | null;
  cex_affordability_available?: boolean | null;
  geography_context?: Record<string, unknown> | null;
  prior_notes?: Array<Record<string, unknown>>;
  warnings?: string[];
  generation_debug?: Record<string, unknown> | null;
  run_debug_summary?: SimulationRunDebugSummary | null;
  run_conditions?: SimulationRunConditions | null;
  personas?: Array<Record<string, unknown>>;
  response_record_preview?: Array<Record<string, unknown>>;
  response_records?: Array<Record<string, unknown>>;
  survey_parse_warnings?: string[];
};

export type SimulationStabilityResultPayload = {
  repeat_runs: number;
  run_summaries?: Array<Record<string, unknown>>;
  stability_table?: Array<Record<string, unknown>>;
  stability_labels?: string[];
  warnings?: string[];
  used_grounded_priors?: boolean;
  created_at?: string | null;
};

export type AnalysisQuestionOption = {
  id: string;
  text: string;
  question_type?: string;
  response_count?: number;
  question_order?: number;
};

export type AnalysisTrustPayload = {
  question_id?: string;
  confidence_label?: string;
  agreement_label?: string;
  explanation?: string;
};

export type AnalysisDistributionRow = {
  answer_display: string;
  count: number;
  percentage: number;
};

export type AnalysisDashboardDistributionRow = {
  label: string;
  count: number;
  percentage: number;
};

export type AnalysisDashboardHistogramBin = {
  label: string;
  count: number;
  start?: number;
  end?: number;
};

export type AnalysisDashboardLinePoint = {
  label: string;
  count: number;
  value?: string;
};

export type AnalysisDashboardWordCloudTerm = {
  term: string;
  count: number;
  weight: number;
};

export type AnalysisDashboardQuote = {
  text: string;
  respondent_id?: string | null;
  model?: string | null;
};

export type AnalysisDashboardQuestion = {
  question_id: string;
  question_text: string;
  question_type?: string;
  question_order: number;
  response_count: number;
  chart_kind:
    | "categorical_bar"
    | "likert"
    | "histogram"
    | "line"
    | "word_cloud";
  distribution?: AnalysisDashboardDistributionRow[];
  histogram_bins?: AnalysisDashboardHistogramBin[];
  line_points?: AnalysisDashboardLinePoint[];
  word_cloud_terms?: AnalysisDashboardWordCloudTerm[];
  quotes?: AnalysisDashboardQuote[];
};

export type AnalysisResponseRecord = {
  respondent_id?: string;
  model?: string;
  survey_title?: string | null;
  question_id?: string;
  question_text?: string;
  question_type?: string;
  answer?: unknown;
  segment_label?: string | null;
};

export type AnalysisPayload = {
  available: boolean;
  message?: string;
  transparency_note?: string;
  run?: {
    run_id?: string;
    status?: string;
    survey_title?: string | null;
    experiment_mode?: string;
    created_at?: string | null;
    models_used?: string[];
    requested_responses?: number;
    generated_responses?: number;
  };
  summary?: {
    total_records?: number;
    unique_respondents?: number;
    question_count?: number;
    models_present?: string[];
    segments_present?: string[];
    survey_titles_present?: string[];
    active_segment_summary?: string;
  };
  filters?: {
    question_options?: AnalysisQuestionOption[];
    model_options?: string[];
    segment_options?: string[];
    selected_question_id?: string | null;
    selected_model?: string;
    selected_segment?: string;
    filtered_record_count?: number;
  };
  dashboard?: {
    model_options?: string[];
    selected_model?: string;
    questions?: AnalysisDashboardQuestion[];
  };
  run_debug_summary?: SimulationRunDebugSummary | null;
  benchmark_snapshot?: {
    available?: boolean;
    message?: string;
    models_compared?: string[];
    stability_summary?: string;
    top_use_case_consensus?: string;
    top_barrier_consensus?: string;
    detailed_table?: Array<Record<string, unknown>>;
  };
  realism_scorecard?: {
    available?: boolean;
    message?: string | null;
    summary?: Record<string, unknown> | null;
    question_rows?: Array<Record<string, unknown>>;
  };
  question_explorer?: {
    question_id?: string | null;
    question_text?: string | null;
    question_type?: string | null;
    response_count?: number;
    trust?: AnalysisTrustPayload | null;
    distribution?: AnalysisDistributionRow[];
    stats_summary?: Record<string, unknown> | null;
  };
  open_text?: {
    available?: boolean;
    question_options?: Array<{ id: string; text: string }>;
    selected_question_id?: string | null;
    samples?: AnalysisResponseRecord[];
  };
  records_preview?: {
    total?: number;
    offset?: number;
    limit?: number;
    rows?: AnalysisResponseRecord[];
  };
  context_notes?: {
    run_warnings?: string[];
    survey_parse_warnings?: string[];
  };
};

export type InsightsTopFinding = {
  id: string;
  title: string;
  headline: string;
  summary: string;
  confidence_label?: string;
  agreement_label?: string;
  chart_kind?: string;
  chart_rows?: Array<Record<string, unknown>>;
};

export type InsightsLlmKeyFinding = {
  title: string;
  summary: string;
  why_it_matters: string;
  evidence_ids: string[];
};

export type InsightsLlmSummary = {
  available: boolean;
  message?: string;
  overview?: string;
  key_findings?: InsightsLlmKeyFinding[];
  result_reliability?: {
    level: string;
    summary: string;
    reason: string;
    evidence_ids: string[];
  };
  recommended_next_steps?: string[];
  researcher_note?: string;
  model?: string;
  from_run_id?: string;
  generated_at?: string;
  cached?: boolean;
};

export type InsightsEvidenceItem = {
  id: string;
  category?: string;
  title?: string;
  summary?: string;
  metrics?: Record<string, unknown>;
};

export type InsightsPayload = {
  available: boolean;
  message?: string;
  transparency_note?: string;
  run?: {
    run_id?: string;
    status?: string;
    survey_title?: string | null;
    experiment_mode?: string;
    created_at?: string | null;
    models_used?: string[];
    requested_responses?: number;
    generated_responses?: number;
  };
  executive_summary?: {
    top_use_case?: {
      label?: string;
      share?: number | null;
    };
    average_interest?: number | null;
    strongest_segment?: string | null;
    model_difference?: {
      status?: string;
      differing_questions?: number;
      note?: string;
    };
    records_summary?: {
      total_records?: number;
      unique_respondents?: number;
      questions?: number;
      survey_title?: string | null;
      models_used?: string[];
    };
  };
  trust_snapshot?: {
    confidence_summary?: {
      dominant_label?: string;
      counts?: Record<string, number>;
    };
    agreement_summary?: {
      dominant_label?: string;
      counts?: Record<string, number>;
    };
    realism_snapshot?: {
      available?: boolean;
      label?: string;
      detail?: string | null;
    };
    benchmark_snapshot?: {
      available?: boolean;
      label?: string;
      detail?: string | null;
    };
  };
  top_findings?: InsightsTopFinding[];
  charts?: {
    barrier_ranking?: {
      available?: boolean;
      message?: string;
      rows?: Array<{ question_id?: string; label?: string; value?: number }>;
    };
    message_performance?: {
      available?: boolean;
      message?: string;
      rows?: Array<{
        concept_id?: string;
        label?: string;
        appeal_avg?: number | null;
        purchase_avg?: number | null;
      }>;
    };
    segment_heatmap?: {
      available?: boolean;
      message?: string;
      segments?: string[];
      rows?: Array<{
        question_id?: string;
        label?: string;
        values?: Array<{ segment?: string; value?: number | null }>;
      }>;
    };
    use_case_share?: {
      available?: boolean;
      message?: string;
      rows?: Array<{ label?: string; count?: number; share?: number }>;
    };
    interest_ladder?: {
      available?: boolean;
      message?: string;
      rows?: Array<{ question_id?: string; label?: string; value?: number; measure?: string }>;
    };
    model_difference?: {
      available?: boolean;
      message?: string;
      models?: string[];
      rows?: Array<{
        question_id?: string;
        label?: string;
        spread?: number;
        values?: Array<{ model?: string; value?: number }>;
      }>;
    };
  };
  segment_story?: {
    strongest_segment?: string;
    weakest_segment?: string;
    notes?: string[];
    heatmap_available?: boolean;
  };
  recommendations?: string[];
  context_notes?: {
    model_notes?: string[];
    segment_notes?: string[];
    run_warnings?: string[];
    survey_parse_warnings?: string[];
  };
  llm_summary?: InsightsLlmSummary;
  evidence_package?: {
    version?: string;
    from_run_id?: string;
    run_context?: {
      run_id?: string;
      survey_title?: string | null;
      experiment_mode?: string;
      models_used?: string[];
      respondent_count?: number | null;
      question_count?: number | null;
    };
    items?: InsightsEvidenceItem[];
  };
};

export type SimulationJobPayload<T> = {
  job_id: string;
  job_type: string;
  status: string;
  payload?: Record<string, unknown> | null;
  result?: T | null;
  error?: Record<string, unknown> | null;
  queued_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type CanonicalStudy = {
  study_id: string;
  lifecycle_status: string;
  owner?: {
    owner_user_id?: string | null;
    owner_org_id?: string | null;
  };
  study_mode: {
    status: string;
    value: string | null;
    saved_at?: string | null;
    updated_at?: string | null;
  };
  audience?: {
    status: string;
    value?: AudiencePayload | null;
    saved_at?: string | null;
    updated_at?: string | null;
  };
  product?: {
    status: string;
    value?: ProductPayload | null;
    saved_at?: string | null;
    updated_at?: string | null;
  };
  market?: {
    status: string;
    value?: MarketPayload | null;
    saved_at?: string | null;
    updated_at?: string | null;
  };
  survey?: SurveyApiState;
  experiment?: {
    status: string;
    value?: ExperimentPayload | null;
    saved_at?: string | null;
    updated_at?: string | null;
  };
  product_enrichments?: {
    latest_url_autofill?: ProductEnrichmentSummary | null;
    latest_image_analysis?: ProductEnrichmentSummary | null;
  };
  derived?: {
    workflow?: WorkflowReadiness;
    latest_persona_preview?: PersonaPreviewPayload | null;
  };
  created_at?: string;
  updated_at?: string;
  archived_at?: string | null;
};

export type InsightsResponse = {
  data?: {
    insights?: InsightsPayload;
  };
};

// ---------------------------------------------------------------------------
// Interview types
// ---------------------------------------------------------------------------

export type InterviewQuestion = {
  id: string;
  text: string;
};

export type InterviewSynthesisConfig = {
  questions?: InterviewQuestion[] | null;
  model_a?: string | null;
  model_b?: string | null;
  judge_model?: string | null;
};

export type InterviewDimensionScores = {
  purchase_intent: 0 | 1;
  primary_objection: 0 | 1;
  fit_tier_alignment: 0 | 1;
  use_case_specificity: 0 | 1;
};

export type InterviewPersonaScore = {
  persona_id: string;
  score: number;
  dimension_scores: InterviewDimensionScores;
  has_error: boolean;
};

export type InterviewGroundingReport = {
  corpus_average: number;
  passes_threshold: boolean;
  threshold: number;
  per_dimension_avg: {
    purchase_intent: number;
    primary_objection: number;
    fit_tier_alignment: number;
    use_case_specificity: number;
  };
  flagged_persona_ids: string[];
  persona_scores: InterviewPersonaScore[];
};

export type InterviewAnswers = Record<string, string>;

export type InterviewModelResult = {
  model: string;
  answers: InterviewAnswers;
  error: string | null;
};

export type InterviewPair = {
  persona_id: string;
  persona_index: number;
  persona: Record<string, unknown>;
  model_a: InterviewModelResult;
  model_b: InterviewModelResult;
  generation_timestamp: string;
};

export type InterviewRunPayload = {
  job_id: string;
  status: "running" | "completed" | "failed";
  persona_count: number | null;
  model_a: string | null;
  model_b: string | null;
  grounding_report: InterviewGroundingReport | null;
  pairs: InterviewPair[] | null;
  error: { message?: string } | null;
  queued_at: string | null;
  completed_at: string | null;
};

export type InterviewSynthesisState = {
  status: string;
  value: InterviewSynthesisConfig | null;
  saved_at: string | null;
  updated_at: string | null;
  latest_run: InterviewRunPayload | null;
};

export type ResearchBriefValue = {
  primary_question: string;
  hypotheses: string[];
  decisions_to_inform: string[];
  focus_fit_tiers: string[];
  focus_segments: string[];
  known_context: string | null;
  notes: string | null;
};

export type ResearchBriefState = {
  status: string;
  value: ResearchBriefValue | null;
  saved_at: string | null;
  updated_at: string | null;
};

export type InterviewTheme = {
  label: string;
  count: number;
  synthesis: string;
  representative_quote: string;
  quote_persona_id: string;
  sentiment: "positive" | "neutral" | "negative";
};

export type InterviewInsightsPayload = {
  available: boolean;
  message?: string;
  from_run_id?: string;
  themes?: InterviewTheme[];
  persona_count?: number;
  grounding_corpus_average?: number | null;
  grounding_passes_threshold?: boolean | null;
};

export type InterviewChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type InterviewChatPayload = {
  persona_id: string;
  prompt: string;
  messages?: InterviewChatMessage[];
  transcript_source?: "model_a" | "model_b";
  model?: string;
};

export type InterviewChatResponse = {
  persona_id: string;
  transcript_source: "model_a" | "model_b";
  model: string | null;
  source_run_id: string;
  reply: string;
};

export type GetStudyResponse = {
  data?: {
    study?: CanonicalStudy;
  };
};

function normalizeCanonicalStudy(study: CanonicalStudy): CanonicalStudy {
  if (!study.survey) {
    return study;
  }

  return {
    ...study,
    survey: {
      ...study.survey,
      schema: study.survey.schema ?? study.survey.schema_ ?? null,
    },
  };
}

function normalizeSurveyResponse(survey?: SurveyApiState | null) {
  if (!survey) {
    return null;
  }

  return {
    ...survey,
    schema: survey.schema ?? survey.schema_ ?? null,
  };
}

export type PatchStudyModeResponse = {
  data?: {
    study_mode?: {
      status?: string;
      value?: string | null;
      saved_at?: string | null;
      updated_at?: string | null;
    };
    study_lifecycle_status?: string;
  };
};

export type PatchAudienceResponse = {
  data?: {
    audience?: {
      status?: string;
      value?: AudiencePayload | null;
      saved_at?: string | null;
      updated_at?: string | null;
    };
    workflow?: WorkflowReadiness;
  };
};

export type PatchProductResponse = {
  data?: {
    product?: {
      status?: string;
      value?: ProductPayload | null;
      saved_at?: string | null;
      updated_at?: string | null;
    };
    workflow?: WorkflowReadiness;
  };
};

export type PatchMarketResponse = {
  data?: {
    market?: {
      status?: string;
      value?: MarketPayload | null;
      saved_at?: string | null;
      updated_at?: string | null;
    };
    workflow?: WorkflowReadiness;
  };
};

export type PatchExperimentResponse = {
  data?: {
    experiment?: {
      status?: string;
      value?: ExperimentPayload | null;
      saved_at?: string | null;
      updated_at?: string | null;
    };
    workflow?: WorkflowReadiness;
  };
};

export type ProductUrlAutofillResponse = {
  data?: {
    enrichment?: ProductEnrichmentSummary;
    product?: {
      status?: string;
      value?: ProductPayload | null;
      saved_at?: string | null;
      updated_at?: string | null;
    };
  };
};

export type ProductImageAnalysisResponse = {
  data?: {
    asset?: {
      asset_id?: string;
      original_filename?: string;
      mime_type?: string;
    };
    enrichment?: ProductEnrichmentSummary;
    product?: {
      status?: string;
      value?: ProductPayload | null;
      saved_at?: string | null;
      updated_at?: string | null;
    };
  };
};

export type SurveyUploadResponse = {
  data?: {
    asset?: {
      asset_id?: string;
      original_filename?: string;
      mime_type?: string;
    };
    survey?: SurveyApiState;
    workflow?: WorkflowReadiness;
  };
};

export type PersonaPreviewResponse = {
  data?: {
    persona_preview?: PersonaPreviewPayload | null;
    workflow?: WorkflowReadiness;
  };
};

export type PromptPreviewResponse = {
  data?: {
    prompt_preview?: PromptPreviewPayload | null;
  };
};

export type ModelCatalogResponse = {
  data?: {
    source?: "openrouter" | "fallback";
    warning?: string | null;
    models?: ModelCatalogEntry[];
  };
};

export type SimulationRunResponse = {
  data?: {
    simulation_run?: SimulationJobPayload<SimulationRunResultPayload> | null;
    workflow?: WorkflowReadiness | null;
  };
};

export type StabilityCheckResponse = {
  data?: {
    stability_check?: SimulationJobPayload<SimulationStabilityResultPayload> | null;
  };
};

export type ClearSimulationRunResponse = {
  data?: {
    cleared?: number;
  };
};

export type AnalysisResponse = {
  data?: {
    analysis?: AnalysisPayload;
  };
};

export async function createStudy() {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    throw new Error(`Study bootstrap failed with status ${response.status}`);
  }

  const payload = (await response.json()) as CreateStudyResponse;
  const studyId = payload.data?.study?.study_id;

  if (!studyId) {
    throw new Error("Study bootstrap succeeded but no study_id was returned.");
  }

  return studyId;
}

export async function getStudy(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Study load failed with status ${response.status}`);
  }

  const payload = (await response.json()) as GetStudyResponse;
  const resolvedStudyId = payload.data?.study?.study_id;

  if (!resolvedStudyId) {
    throw new Error("Study load succeeded but no study_id was returned.");
  }

  return resolvedStudyId;
}

export async function getStudyDetails(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Study detail load failed with status ${response.status}`);
  }

  const payload = (await response.json()) as GetStudyResponse;
  const study = payload.data?.study;

  if (!study?.study_id) {
    throw new Error("Study detail load succeeded but no canonical study was returned.");
  }

  return normalizeCanonicalStudy(study);
}

export async function saveStudyMode(studyId: string, studyMode: "neo_smart" | "general") {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/study-mode`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      study_mode: studyMode,
    }),
  });

  if (!response.ok) {
    throw new Error(`Study mode save failed with status ${response.status}`);
  }

  const payload = (await response.json()) as PatchStudyModeResponse;
  const value = payload.data?.study_mode?.value;

  if (!value) {
    throw new Error("Study mode save succeeded but no study_mode value was returned.");
  }

  return {
    value,
    status: payload.data?.study_mode?.status ?? "saved",
    lifecycleStatus: payload.data?.study_lifecycle_status ?? "setup_in_progress",
  };
}

export async function bootstrapNeoDemoStudy(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/study-mode/bootstrap/neo`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Neo demo bootstrap failed with status ${response.status}`
      )
    );
  }

  const payload = (await response.json()) as GetStudyResponse;
  const study = payload.data?.study;
  if (!study?.study_id) {
    throw new Error("Neo demo bootstrap succeeded but no canonical study was returned.");
  }

  return normalizeCanonicalStudy(study);
}

export async function saveAudience(studyId: string, payload: AudiencePayload) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/audience`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(response, `Audience save failed with status ${response.status}`)
    );
  }

  const result = (await response.json()) as PatchAudienceResponse;

  return {
    audience: result.data?.audience,
    workflow: result.data?.workflow,
  };
}

export async function getWorkflow(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/workflow`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Workflow load failed with status ${response.status}`);
  }

  const payload = (await response.json()) as {
    data?: {
      workflow?: WorkflowReadiness;
    };
  };

  return payload.data?.workflow ?? null;
}

export async function saveProduct(studyId: string, payload: ProductPayload) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/product`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(response, `Product save failed with status ${response.status}`)
    );
  }

  const result = (await response.json()) as PatchProductResponse;

  return {
    product: result.data?.product,
    workflow: result.data?.workflow,
  };
}

export async function saveMarket(studyId: string, payload: MarketPayload) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/market`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(response, `Market save failed with status ${response.status}`)
    );
  }

  const result = (await response.json()) as PatchMarketResponse;

  return {
    market: result.data?.market,
    workflow: result.data?.workflow,
  };
}

export async function runProductUrlAutofill(studyId: string, url: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/product/url-autofill`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      url,
      apply_to_product: false,
    }),
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Product URL autofill failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as ProductUrlAutofillResponse;
  return {
    enrichment: result.data?.enrichment ?? null,
    product: result.data?.product ?? null,
  };
}

export async function runProductImageAnalysis(studyId: string, file: File) {
  const apiBaseUrl = getApiBaseUrl();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("apply_to_product", "false");

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/product/image-analysis`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Product image analysis failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as ProductImageAnalysisResponse;
  return {
    asset: result.data?.asset ?? null,
    enrichment: result.data?.enrichment ?? null,
    product: result.data?.product ?? null,
  };
}

export async function uploadSurvey(studyId: string, file: File) {
  const apiBaseUrl = getApiBaseUrl();
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/survey/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readApiErrorMessage(response, `Survey upload failed with status ${response.status}`));
  }

  const result = (await response.json()) as SurveyUploadResponse;
  return {
    asset: result.data?.asset ?? null,
    survey: normalizeSurveyResponse(result.data?.survey),
    workflow: result.data?.workflow ?? null,
  };
}

export async function loadNeoSurveyPreset(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/survey/preset/neo`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(response, `Neo survey preset load failed with status ${response.status}`)
    );
  }

  const result = (await response.json()) as SurveyUploadResponse;
  return {
    asset: result.data?.asset ?? null,
    survey: normalizeSurveyResponse(result.data?.survey),
    workflow: result.data?.workflow ?? null,
  };
}

export async function saveExperiment(studyId: string, payload: ExperimentPayload) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/experiment`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Experiment save failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as PatchExperimentResponse;
  return {
    experiment: result.data?.experiment,
    workflow: result.data?.workflow ?? null,
  };
}

export async function getModelCatalog() {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/models`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Model catalog load failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as ModelCatalogResponse;
  return {
    source: result.data?.source ?? "fallback",
    warning: result.data?.warning ?? null,
    models: result.data?.models ?? [],
  };
}

export async function generatePersonaPreview(
  studyId: string,
  payload: PersonaPreviewRequest
) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/personas/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Persona preview failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as PersonaPreviewResponse;
  return {
    personaPreview: result.data?.persona_preview ?? null,
    workflow: result.data?.workflow ?? null,
  };
}

export async function getPromptPreview(studyId: string, personaIndex = 0) {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/prompt-preview?persona_index=${encodeURIComponent(String(personaIndex))}`
  );

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Prompt preview failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as PromptPreviewResponse;
  return result.data?.prompt_preview ?? null;
}

export async function startSimulationRun(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/simulation-runs`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Simulation run failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as SimulationRunResponse;
  return {
    simulationRun: result.data?.simulation_run ?? null,
    workflow: result.data?.workflow ?? null,
  };
}

export async function getLatestSimulationRun(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/simulation-runs/latest`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Latest simulation run load failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as SimulationRunResponse;
  return result.data?.simulation_run ?? null;
}

export async function clearLatestSimulationRun(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/simulation-runs/latest`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Simulation clear failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as ClearSimulationRunResponse;
  return {
    cleared: result.data?.cleared ?? 0,
  };
}

export async function startStabilityCheck(studyId: string, repeatRuns: number) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/simulation-runs/stability`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ repeat_runs: repeatRuns }),
    }
  );

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Stability check failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as StabilityCheckResponse;
  return result.data?.stability_check ?? null;
}

export async function getLatestStabilityCheck(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/simulation-runs/stability/latest`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Latest stability check load failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as StabilityCheckResponse;
  return result.data?.stability_check ?? null;
}

export async function getAnalysis(
  studyId: string,
  params?: {
    questionId?: string | null;
    model?: string | null;
    segment?: string | null;
    recordsLimit?: number;
    recordsOffset?: number;
    openTextLimit?: number;
  }
) {
  const apiBaseUrl = getApiBaseUrl();
  const searchParams = new URLSearchParams();

  if (params?.questionId) {
    searchParams.set("question_id", params.questionId);
  }
  if (params?.model && params.model !== "All") {
    searchParams.set("model", params.model);
  }
  if (params?.segment && params.segment !== "All") {
    searchParams.set("segment", params.segment);
  }
  if (typeof params?.recordsLimit === "number") {
    searchParams.set("records_limit", String(params.recordsLimit));
  }
  if (typeof params?.recordsOffset === "number") {
    searchParams.set("records_offset", String(params.recordsOffset));
  }
  if (typeof params?.openTextLimit === "number") {
    searchParams.set("open_text_limit", String(params.openTextLimit));
  }

  const query = searchParams.toString();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/analysis${query ? `?${query}` : ""}`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    }
  );

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Analysis load failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as AnalysisResponse;
  return result.data?.analysis ?? { available: false };
}

export async function getInsights(studyId: string) {
  const apiBaseUrl = getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/insights`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Insights load failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as InsightsResponse;
  return result.data?.insights ?? { available: false };
}

// ---------------------------------------------------------------------------
// Interview fetch functions
// ---------------------------------------------------------------------------

export async function getInterviewSynthesis(studyId: string): Promise<InterviewSynthesisState> {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/synthesis`,
    { method: "GET", headers: { Accept: "application/json" }, cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Interview synthesis load failed with status ${response.status}`
      )
    );
  }
  const result = (await response.json()) as {
    data?: { interview_synthesis?: InterviewSynthesisState };
  };
  return (
    result.data?.interview_synthesis ?? {
      status: "not_started",
      value: null,
      saved_at: null,
      updated_at: null,
      latest_run: null,
    }
  );
}

export async function saveInterviewSynthesisConfig(
  studyId: string,
  payload: InterviewSynthesisConfig
) {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/synthesis`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Interview synthesis save failed with status ${response.status}`
      )
    );
  }
  const result = (await response.json()) as {
    data?: { interview_synthesis?: Omit<InterviewSynthesisState, "latest_run"> };
  };
  return result.data?.interview_synthesis ?? null;
}

export async function startInterviewRun(
  studyId: string,
  payload?: Partial<InterviewSynthesisConfig>
): Promise<InterviewRunPayload | null> {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/runs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    }
  );
  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Interview run failed with status ${response.status}`
      )
    );
  }
  const result = (await response.json()) as {
    data?: { interview_run?: InterviewRunPayload };
  };
  return result.data?.interview_run ?? null;
}

export async function getLatestInterviewRun(
  studyId: string
): Promise<InterviewRunPayload | null> {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/runs/latest`,
    { method: "GET", headers: { Accept: "application/json" }, cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Interview run load failed with status ${response.status}`
      )
    );
  }
  const result = (await response.json()) as {
    data?: { interview_run?: InterviewRunPayload | null };
  };
  return result.data?.interview_run ?? null;
}

export async function getResearchBrief(studyId: string): Promise<ResearchBriefState> {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/brief`,
    { method: "GET", headers: { Accept: "application/json" }, cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Research brief load failed with status ${response.status}`
      )
    );
  }
  const result = (await response.json()) as {
    data?: { research_brief?: ResearchBriefState };
  };
  return (
    result.data?.research_brief ?? {
      status: "not_started",
      value: null,
      saved_at: null,
      updated_at: null,
    }
  );
}

export async function saveResearchBrief(
  studyId: string,
  payload: Partial<ResearchBriefValue>
) {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/brief`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Research brief save failed with status ${response.status}`
      )
    );
  }
  const result = (await response.json()) as {
    data?: { research_brief?: ResearchBriefState };
  };
  return result.data?.research_brief ?? null;
}

export async function getInterviewInsights(
  studyId: string
): Promise<InterviewInsightsPayload> {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/insights`,
    { method: "GET", headers: { Accept: "application/json" }, cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Interview insights load failed with status ${response.status}`
      )
    );
  }
  const result = (await response.json()) as {
    data?: { interview_insights?: InterviewInsightsPayload };
  };
  return result.data?.interview_insights ?? { available: false };
}

export async function sendInterviewChatMessage(
  studyId: string,
  payload: InterviewChatPayload
): Promise<InterviewChatResponse> {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(
    `${apiBaseUrl}/api/v1/studies/${studyId}/interview/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    throw new Error(
      await readApiErrorMessage(
        response,
        `Interview chat failed with status ${response.status}`
      )
    );
  }

  const result = (await response.json()) as {
    data?: { interview_chat?: InterviewChatResponse };
  };
  if (!result.data?.interview_chat) {
    throw new Error("Interview chat returned an empty response.");
  }
  return result.data.interview_chat;
}
