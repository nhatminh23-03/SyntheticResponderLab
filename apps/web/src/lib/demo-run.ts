type RunLike = { generation_mode?: string | null; warnings?: string[] | null; demo?: { reason?: string } | null };

export function describeDemoRun(result: RunLike | null | undefined): { reason: string; message: string } | null {
  if (!result || result.generation_mode !== "demo_preloaded") return null;
  const warnings = result.warnings ?? [];
  return { reason: result.demo?.reason ?? "requested", message: [warnings[0], warnings[1]].filter(Boolean).join(" ") };
}
