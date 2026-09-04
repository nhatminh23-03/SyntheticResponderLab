import type { InterviewModelCatalogEntry } from "./api";


export function formatInterviewModelOption(model: InterviewModelCatalogEntry) {
  const tier = model.tier[0].toUpperCase() + model.tier.slice(1);
  const prompt = model.prompt_price_per_million.toFixed(2);
  const completion = model.completion_price_per_million.toFixed(2);
  return `${tier} · ${model.name} · $${prompt} in / $${completion} out per 1M tokens`;
}

export function isInterviewModelSelectable(
  model: InterviewModelCatalogEntry,
  expensiveOptIn: boolean
) {
  return model.tier !== "expensive" || expensiveOptIn;
}

export function resetExpensiveModelSelection(
  models: InterviewModelCatalogEntry[],
  selectedModelId: string,
  defaultModelId: string
) {
  const selected = models.find((model) => model.id === selectedModelId);
  return selected?.tier === "expensive" ? defaultModelId : selectedModelId;
}

export function estimateInterviewRunCost(
  personaCount: number,
  interviewerModel: InterviewModelCatalogEntry,
  intervieweeModel: InterviewModelCatalogEntry
) {
  return (
    personaCount *
    (interviewerModel.estimated_cost_per_persona_usd +
      intervieweeModel.estimated_cost_per_persona_usd)
  );
}

export function formatInterviewRunCostEstimate(costUsd: number) {
  return `$${costUsd.toFixed(3)}`;
}
