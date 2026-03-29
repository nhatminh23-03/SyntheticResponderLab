export type ChartTone = "cyan" | "gold" | "neutral";

export type ChartBadge = {
  label: string;
  tone?: ChartTone;
};

export type RankedBarDatum = {
  id: string;
  label: string;
  value: number;
  valueLabel?: string;
  emphasis?: boolean;
  meta?: string;
};

export type GroupedBarSeriesDatum = {
  key: string;
  label: string;
  value: number | null;
  valueLabel?: string;
  tone?: ChartTone;
};

export type GroupedBarDatum = {
  id: string;
  label: string;
  series: GroupedBarSeriesDatum[];
};

export type HeatmapColumn = {
  key: string;
  label: string;
};

export type HeatmapCell = {
  key: string;
  label: string;
  value: number | null;
  valueLabel?: string;
};

export type HeatmapDatum = {
  id: string;
  label: string;
  values: HeatmapCell[];
};

export type StepDatum = {
  id: string;
  label: string;
  value: number;
  valueLabel?: string;
  meta?: string;
};

export type ModelDifferenceDatum = {
  id: string;
  label: string;
  spread: number;
  spreadLabel?: string;
  values: Array<{
    model: string;
    value: number;
    valueLabel?: string;
  }>;
};
