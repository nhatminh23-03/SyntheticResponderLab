type RunLike = { generation_mode?: string | null; warnings?: string[] | null; demo?: { reason?: string } | null };

export const DEMO_GENERATION_MODE = "demo_preloaded";
export const ADDED_QUESTIONS_NOT_IN_DEMO = "Your added questions are not in the preloaded demo.";

export function describeDemoRun(result: RunLike | null | undefined): { reason: string; message: string } | null {
  if (!result || !isDemoGenerationMode(result.generation_mode)) return null;
  const warnings = result.warnings ?? [];
  return { reason: result.demo?.reason ?? "requested", message: [warnings[0], warnings[1]].filter(Boolean).join(" ") };
}

/** The demo banner's lines: the demo message, then every remaining warning ("Run live to answer these: SQ1", "Detail: ..."). */
export function demoBannerLines(result: RunLike | null | undefined): string[] {
  const demo = describeDemoRun(result);
  if (!demo) return [];
  const rest = (result?.warnings ?? []).slice(2).filter(Boolean);
  return [demo.message, ...rest].filter(Boolean);
}

/** A run is the preloaded demo only when the API says so in its generation_mode. */
export function isDemoGenerationMode(mode: string | null | undefined): boolean {
  return mode === DEMO_GENERATION_MODE;
}

/** An extra line for a run error: only the "needs a live run" refusals say the preloaded demo lacks the student's questions. */
export function runErrorNote(message: string): string | null {
  return message.includes("requires a live run") ? ADDED_QUESTIONS_NOT_IN_DEMO : null;
}
