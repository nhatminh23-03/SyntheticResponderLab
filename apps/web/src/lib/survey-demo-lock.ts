import type { RunControl } from "./backend-readiness";
import { DEMO_READ_ONLY, isDemoMode } from "./demo-mode";

/**
 * The app-wide Demo (no AI) switch on the survey workflow page ('/').
 *
 * The switch lives in the browser; the server cannot see it. So every action on this page that reaches an AI provider
 * is locked here twice: its button is disabled with a note, and its click handler refuses it if it is called anyway.
 * Everything else on the page (saving sections, uploading a survey, the Neo preset, student questions, results) stays
 * open. The two insight reads that can call a model on GET are sent with `ai=false` instead (see aiReadOptions).
 */
export type SurveyAiAction =
  /** POST simulation-runs with source "live" (Jev or OpenRouter). The preloaded demo is not an AI action. */
  | "run_live"
  /** POST simulation-runs/stability: repeated OpenRouter runs. */
  | "stability_check"
  /** POST product/url-autofill: an OpenRouter model drafts the product from the page text when a key is set. */
  | "product_url_autofill"
  /** POST product/image-analysis: Google Vision or an OpenRouter model reads the image. */
  | "product_image_analysis"
  /** POST survey/generate: an OpenRouter model drafts or revises the survey. */
  | "survey_generate"
  /** POST interview/runs: two OpenRouter models and a judge, except a Neo study, which loads seeded transcripts. */
  | "interview_run"
  /** POST interview/chat: an OpenRouter model answers in character. */
  | "interview_chat";

export const SURVEY_AI_ACTIONS: readonly SurveyAiAction[] = [
  "run_live",
  "stability_check",
  "product_url_autofill",
  "product_image_analysis",
  "survey_generate",
  "interview_run",
  "interview_chat",
];

export const DEMO_RUN_LIVE_NOTE = `${DEMO_READ_ONLY}. Turn Demo off at the top of the page to run live.`;
export const DEMO_AI_ACTION_NOTE = `${DEMO_READ_ONLY}. Turn Demo off at the top of the page to use this.`;
export const DEMO_ADDED_QUESTIONS_NOTE =
  "Added questions need a live run — turn Demo off at the top of the page to answer them.";
/** The add-question card's success line with the switch off. */
export const ADDED_QUESTION_STATUS = "Added. Run live to get answers to it.";

/** The study mode whose interview run is served from seeded transcripts on the server, with no model call. */
const SEEDED_INTERVIEW_STUDY_MODE = "neo_smart";

/**
 * The switch as a click handler or an effect should read it: the rendered value, or the stored one when a render has
 * not caught up yet (the first render after a reload always reports the switch off).
 */
export function demoSwitchOn(rendered: boolean): boolean {
  return rendered || isDemoMode();
}

/** True when the switch locks this action. An unknown study mode keeps the interview run locked. */
export function isSurveyActionLocked(action: SurveyAiAction, demoOn: boolean, studyMode?: string | null): boolean {
  if (!demoOn) return false;
  if (action === "interview_run") return studyMode !== SEEDED_INTERVIEW_STUDY_MODE;
  return true;
}

/** The one-line note shown next to a locked control. */
export function demoLockNote(action: SurveyAiAction): string {
  return action === "run_live" ? DEMO_RUN_LIVE_NOTE : DEMO_AI_ACTION_NOTE;
}

/** Click-time guard: the note to show when the switch refuses the action, or null when it may go ahead. */
export function refuseIfDemoLocked(action: SurveyAiAction, demoOn: boolean, studyMode?: string | null): string | null {
  return isSurveyActionLocked(action, demoOn, studyMode) ? demoLockNote(action) : null;
}

/**
 * The Run step's two buttons with the switch applied. Off: both come back untouched. On: Run live is disabled and the
 * preloaded demo is unchanged. The locked button's readiness hint is dropped (the lock note replaces it), unless the
 * demo is off too: then that hint is the one that says why both are unavailable.
 */
export function applyDemoLockToRunControls<L extends RunControl>(
  demoOn: boolean,
  live: L,
  demo: RunControl
): { live: L; demo: RunControl } {
  if (!demoOn) return { live, demo };
  return { live: { ...live, enabled: false, hint: demo.enabled ? null : live.hint }, demo };
}

/** Options for a read that can call a model on GET: with the switch on, the server serves cached AI output only. */
export function aiReadOptions(demoOn: boolean): { ai: boolean } {
  return { ai: !demoOn };
}

/**
 * True when the switch kept the Insights read from generating an AI summary: it is on and no cached summary came back.
 * A cached summary is still served with the switch on, and it is still the LLM's.
 */
export function isAiSummaryWithheld(demoOn: boolean, llmSummaryAvailable: boolean | null | undefined): boolean {
  return demoOn && !llmSummaryAvailable;
}

/**
 * The add-question card's status line as shown. With the switch on, the success line drops "Run live to get answers to
 * it": Run live is locked, and the note above the form already says added questions need a live run.
 */
export function addedQuestionStatus(message: string | null, demoOn: boolean): string | null {
  return demoOn && message === ADDED_QUESTION_STATUS ? "Added." : message;
}
