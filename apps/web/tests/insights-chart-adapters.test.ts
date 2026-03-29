import test from "node:test";
import assert from "node:assert/strict";

import {
  toBarrierRankingRows,
  toHeatmapModel,
  toMessagePerformanceRows,
  toModelDifferenceModel,
} from "../src/lib/insights-chart-adapters";

test("toBarrierRankingRows sorts barrier values descending", () => {
  const rows = toBarrierRankingRows({
    available: true,
    charts: {
      barrier_ranking: {
        available: true,
        rows: [
          { question_id: "Q5_2", label: "Permitting", value: 3.1 },
          { question_id: "Q5_1", label: "Price", value: 4.6 },
        ],
      },
    },
  });

  assert.equal(rows[0]?.id, "Q5_1");
  assert.equal(rows[1]?.id, "Q5_2");
});

test("toMessagePerformanceRows preserves appeal and purchase values", () => {
  const rows = toMessagePerformanceRows({
    available: true,
    charts: {
      message_performance: {
        available: true,
        rows: [
          {
            concept_id: "Q10",
            label: "Concept 10",
            appeal_avg: 4.2,
            purchase_avg: 3.8,
          },
        ],
      },
    },
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.series[0]?.value, 4.2);
  assert.equal(rows[0]?.series[1]?.value, 3.8);
});

test("toHeatmapModel preserves columns and null values", () => {
  const model = toHeatmapModel({
    available: true,
    charts: {
      segment_heatmap: {
        available: true,
        segments: ["Remote", "Wellness"],
        rows: [
          {
            question_id: "Q1",
            label: "Interest",
            values: [
              { segment: "Remote", value: 4.5 },
              { segment: "Wellness", value: null },
            ],
          },
        ],
      },
    },
  });

  assert.ok(model);
  assert.equal(model?.columns.length, 2);
  assert.equal(model?.rows[0]?.values[1]?.value, null);
  assert.equal(model?.rows[0]?.values[1]?.valueLabel, "n/a");
});

test("toModelDifferenceModel returns null when multi-model coverage is missing", () => {
  const model = toModelDifferenceModel({
    available: true,
    charts: {
      model_difference: {
        available: false,
        models: ["openai/gpt-4o-mini"],
        rows: [],
      },
    },
  });

  assert.equal(model, null);
});
