export const JEV_MODEL_ID = "typesafe/jev";
export const JEV_MODEL_LABEL = "Jev — fast, approximate (answers drawn from its probabilities)";

export function toggleModel(selected: string[], modelId: string): string[] {
  if (modelId === JEV_MODEL_ID) return selected.includes(JEV_MODEL_ID) ? [] : [JEV_MODEL_ID];
  const others = selected.filter((id) => id !== JEV_MODEL_ID);
  return others.includes(modelId) ? others.filter((id) => id !== modelId) : [...others, modelId];
}

export function normalizeSelectedModels(selected: string[], fallback: string[], jevAvailable: boolean): string[] {
  if (selected.length === 1 && selected[0] === JEV_MODEL_ID) return jevAvailable ? selected : fallback;
  const others = selected.filter((id) => id !== JEV_MODEL_ID);
  if (others.length >= 2) return others;
  return jevAvailable ? [JEV_MODEL_ID] : fallback;
}

/** The client-side model rule: two or more models, except that Jev runs on its own (split or mirror, never stability). */
export function selectedModelsProblem(selected: string[], experimentMode: string): string | null {
  const loneJev = selected.length === 1 && selected[0] === JEV_MODEL_ID;
  if (loneJev && experimentMode === "stability") return "Jev runs use split or mirror mode, not stability.";
  if (loneJev) return null;
  if (selected.length < 2) return "Select at least 2 models.";
  return null;
}
