import type { GroupedBarDatum, HeatmapColumn, HeatmapDatum, ModelDifferenceDatum, RankedBarDatum, StepDatum } from "../components/charts/chart-types";
import type { InsightsPayload, InsightsTopFinding } from "./api";
import { formatNumber, formatPercent } from "./chart-format";

export function toBarrierRankingRows(payload: InsightsPayload): RankedBarDatum[] {
  const rows = payload.charts?.barrier_ranking?.rows ?? [];
  return [...rows]
    .filter((row) => typeof row.value === "number")
    .sort((left, right) => (right.value ?? 0) - (left.value ?? 0))
    .map((row, index) => ({
      id: row.question_id ?? `barrier-${index}`,
      label: row.label ?? `Barrier ${index + 1}`,
      value: row.value ?? 0,
      valueLabel: formatNumber(row.value ?? 0),
      emphasis: index === 0,
    }));
}

export function toUseCaseShareRows(payload: InsightsPayload): RankedBarDatum[] {
  const rows = payload.charts?.use_case_share?.rows ?? [];
  return [...rows]
    .filter((row) => typeof row.share === "number")
    .sort((left, right) => (right.share ?? 0) - (left.share ?? 0))
    .map((row, index) => ({
      id: row.label ?? `use-case-${index}`,
      label: row.label ?? `Use case ${index + 1}`,
      value: row.share ?? 0,
      valueLabel: formatPercent(row.share ?? 0),
      emphasis: index === 0,
      meta: typeof row.count === "number" ? `${row.count} responses` : undefined,
    }));
}

export function toMessagePerformanceRows(payload: InsightsPayload): GroupedBarDatum[] {
  const rows = payload.charts?.message_performance?.rows ?? [];
  return rows.map((row, index) => ({
    id: row.concept_id ?? `concept-${index}`,
    label: row.label ?? `Concept ${index + 1}`,
    series: [
      {
        key: "appeal",
        label: "Appeal",
        value: row.appeal_avg ?? null,
        valueLabel:
          typeof row.appeal_avg === "number" ? formatNumber(row.appeal_avg) : "n/a",
        tone: "cyan",
      },
      {
        key: "purchase",
        label: "Purchase",
        value: row.purchase_avg ?? null,
        valueLabel:
          typeof row.purchase_avg === "number"
            ? formatNumber(row.purchase_avg)
            : "n/a",
        tone: "gold",
      },
    ],
  }));
}

export function toHeatmapModel(payload: InsightsPayload): {
  columns: HeatmapColumn[];
  rows: HeatmapDatum[];
} | null {
  const chart = payload.charts?.segment_heatmap;
  if (!chart?.available || !chart.segments?.length || !chart.rows?.length) {
    return null;
  }

  return {
    columns: chart.segments.map((segment) => ({ key: segment, label: segment })),
    rows: chart.rows.map((row, index) => ({
      id: row.question_id ?? `heatmap-${index}`,
      label: row.label ?? `Question ${index + 1}`,
      values: (row.values ?? []).map((entry) => ({
        key: entry.segment ?? `segment-${index}`,
        label: entry.segment ?? "Segment",
        value: entry.value ?? null,
        valueLabel:
          typeof entry.value === "number" ? formatNumber(entry.value) : "n/a",
      })),
    })),
  };
}

export function toInterestLadderSteps(payload: InsightsPayload): StepDatum[] {
  const rows = payload.charts?.interest_ladder?.rows ?? [];
  return rows.map((row, index) => ({
    id: row.question_id ?? `step-${index}`,
    label: row.label ?? `Step ${index + 1}`,
    value: row.value ?? 0,
    valueLabel:
      typeof row.value === "number" ? formatPercent(row.value, 1) : "n/a",
  }));
}

export function toModelDifferenceModel(payload: InsightsPayload): {
  models: string[];
  rows: ModelDifferenceDatum[];
} | null {
  const chart = payload.charts?.model_difference;
  if (!chart?.available || !chart.models || chart.models.length < 2) {
    return null;
  }

  return {
    models: chart.models,
    rows: (chart.rows ?? []).map((row, index) => ({
      id: row.question_id ?? `difference-${index}`,
      label: row.label ?? `Question ${index + 1}`,
      spread: row.spread ?? 0,
      spreadLabel:
        typeof row.spread === "number" ? `spread ${formatNumber(row.spread)}` : undefined,
      values: (row.values ?? []).map((entry) => ({
        model: entry.model ?? "Model",
        value: entry.value ?? 0,
        valueLabel:
          typeof entry.value === "number" ? formatNumber(entry.value) : "n/a",
      })),
    })),
  };
}

export function toFindingChartModel(finding: InsightsTopFinding):
  | { kind: "ranked"; rows: RankedBarDatum[] }
  | { kind: "grouped"; rows: GroupedBarDatum[] }
  | { kind: "ladder"; steps: StepDatum[] }
  | null {
  const rows = finding.chart_rows ?? [];

  if (finding.chart_kind === "grouped_bar") {
    return {
      kind: "grouped",
      rows: rows.map((row, index) => ({
        id: String(row.id ?? row.concept_id ?? `group-${index}`),
        label: String(row.label ?? `Item ${index + 1}`),
        series: [
          {
            key: "appeal",
            label: "Appeal",
            value: typeof row.appeal_avg === "number" ? row.appeal_avg : null,
            valueLabel:
              typeof row.appeal_avg === "number" ? formatNumber(row.appeal_avg) : "n/a",
            tone: "cyan",
          },
          {
            key: "purchase",
            label: "Purchase",
            value: typeof row.purchase_avg === "number" ? row.purchase_avg : null,
            valueLabel:
              typeof row.purchase_avg === "number"
                ? formatNumber(row.purchase_avg)
                : "n/a",
            tone: "gold",
          },
        ],
      })),
    };
  }

  if (finding.chart_kind === "ladder") {
    return {
      kind: "ladder",
      steps: rows.map((row, index) => ({
        id: String(row.id ?? row.question_id ?? `step-${index}`),
        label: String(row.label ?? `Step ${index + 1}`),
        value: typeof row.value === "number" ? row.value : 0,
        valueLabel:
          typeof row.value === "number" ? formatPercent(row.value, 1) : "n/a",
      })),
    };
  }

  if (rows.length === 0) {
    return null;
  }

  const rankedRows: RankedBarDatum[] = [];
  rows.forEach((row, index) => {
    const rawValue =
      typeof row.value === "number"
        ? row.value
        : typeof row.share === "number"
        ? row.share
        : null;

    if (rawValue === null) {
      return;
    }

    const usesPercent = typeof row.share === "number";
    rankedRows.push({
      id: String(row.id ?? row.question_id ?? row.label ?? `row-${index}`),
      label: String(row.label ?? row.answer_display ?? `Item ${index + 1}`),
      value: rawValue,
      valueLabel: usesPercent ? formatPercent(rawValue) : formatNumber(rawValue),
      emphasis: index === 0,
    });
  });

  return {
    kind: "ranked",
    rows: rankedRows,
  };
}
