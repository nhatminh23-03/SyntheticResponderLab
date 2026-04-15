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
  { id: "interview-synthesis", label: "Interview Synthesis" },
  { id: "research-brief", label: "Research Brief" },
  { id: "interview-insights", label: "Interview Insights" },
] as const;

export type WorkflowSectionId = (typeof workflowSections)[number]["id"];

// --- Nav group types and data ---

export type NavItemKind = "section" | "coming-soon";

export type NavGroupItem =
  | { kind: "section"; id: WorkflowSectionId; label: string }
  | { kind: "coming-soon"; id: string; label: string };

export type NavGroupVariant = "cyan" | "gold";

export type NavGroup = {
  id: string;
  label: string;
  variant: NavGroupVariant;
  items: NavGroupItem[];
};

export const navGroups: NavGroup[] = [
  {
    id: "setup",
    label: "Setup",
    variant: "cyan",
    items: [
      { kind: "section", id: "study-mode", label: "Study Mode" },
      { kind: "section", id: "audience",   label: "Audience"   },
      { kind: "section", id: "product",    label: "Product"    },
      { kind: "section", id: "market",     label: "Market"     },
    ],
  },
  {
    id: "design",
    label: "Design",
    variant: "cyan",
    items: [
      { kind: "section", id: "survey",     label: "Survey"     },
      { kind: "section", id: "experiment", label: "Experiment" },
    ],
  },
  {
    id: "results",
    label: "Results",
    variant: "cyan",
    items: [
      { kind: "section", id: "analysis", label: "Analysis" },
      { kind: "section", id: "insights", label: "Insights" },
    ],
  },
  {
    id: "interview",
    label: "Interview",
    variant: "gold",
    items: [
      { kind: "section", id: "interview-synthesis", label: "Interview Synthesis" },
      { kind: "section", id: "research-brief",      label: "Research Brief"      },
      { kind: "section", id: "interview-insights",  label: "Interview Insights"  },
    ],
  },
];
