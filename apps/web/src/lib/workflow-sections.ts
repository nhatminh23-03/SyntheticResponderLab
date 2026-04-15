export const workflowSections = [
  { id: "main", label: "Main" },
  { id: "study-mode", label: "Study Mode" },
  { id: "audience", label: "Audience" },
  { id: "product", label: "Product" },
  { id: "market", label: "Market" },
  { id: "survey", label: "Survey" },
  { id: "experiment", label: "Experiment" },
  { id: "run-simulation", label: "Run" },
  { id: "analysis", label: "Analysis" },
  { id: "insights", label: "Insights" },
  { id: "interview-synthesis", label: "Interview Synthesis", showInNav: false },
  { id: "research-brief", label: "Research Brief", showInNav: false },
  { id: "interview-insights", label: "Interview Insights", showInNav: false },
] as const;

export type WorkflowSectionId = (typeof workflowSections)[number]["id"];
