# Phase 3 Insights Chart System Plan

## Purpose

This document turns the Insights graph proposal into a concrete implementation plan for the current Next.js codebase under `SyntheticResponderLab/apps/web`.

The goal is to add a premium, reusable chart system for the Insights chapter without introducing a heavyweight generic charting library.

## Why this approach

The current frontend stack in [apps/web/package.json](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/package.json) does not include a chart library.

That is a good fit for the current product because:

- the needed chart set is small and known
- the charts are product-specific, not open-ended BI tooling
- a custom SVG/CSS chart layer will match the premium visual system better
- we avoid adding a large dependency before we know we need it

## Recommendation

Use a lightweight in-house chart system built from:

- React
- SVG for bars, tracks, lines, and grouped comparisons
- CSS grid for the heatmap
- Framer Motion for restrained reveal/load animation

Do not add `recharts` or another charting dependency in the first pass.

## Target files

### 1. Shared chart shell

Create:

- [chart-frame.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/charts/chart-frame.tsx)

Responsibility:

- shared visual wrapper for all Insights charts
- title
- subtitle / helper line
- legend area
- empty state slot
- source / note row
- optional footer row

Recommended props:

```ts
type ChartFrameProps = {
  title: string;
  subtitle?: string;
  badges?: Array<{ label: string; tone?: "cyan" | "gold" | "neutral" }>;
  empty?: boolean;
  emptyMessage?: string;
  note?: string;
  children?: React.ReactNode;
};
```

Design notes:

- reuse current glass-panel treatment
- keep chart title hierarchy consistent with Insights cards
- every chart should look like the same system, not one-off blocks

### 2. Shared chart primitives

Create:

- [chart-scale.ts](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/lib/chart-scale.ts)
- [chart-format.ts](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/lib/chart-format.ts)

Responsibility:

- normalize numbers
- clamp scale values
- percent formatting
- decimal formatting
- label truncation helpers
- color interpolation for heatmap intensity

Suggested functions:

```ts
export function normalizeRatio(value: number, max: number): number
export function formatPercent(value: number, digits?: number): string
export function formatNumber(value: number, digits?: number): string
export function truncateLabel(label: string, maxLength?: number): string
export function heatmapOpacity(value: number | null, min: number, max: number): number
```

### 3. Shared chart types

Create:

- [chart-types.ts](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/charts/chart-types.ts)

Responsibility:

- define reusable presentational types used by chart components

Suggested types:

```ts
export type RankedBarDatum = {
  id: string;
  label: string;
  value: number;
  valueLabel?: string;
};

export type GroupedBarDatum = {
  id: string;
  label: string;
  series: Array<{
    key: string;
    label: string;
    value: number | null;
  }>;
};

export type HeatmapDatum = {
  id: string;
  label: string;
  values: Array<{
    key: string;
    label: string;
    value: number | null;
  }>;
};

export type StepDatum = {
  id: string;
  label: string;
  value: number;
  valueLabel?: string;
};
```

## Chart components

### 4. Horizontal bar chart

Create:

- [horizontal-bar-chart.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/charts/horizontal-bar-chart.tsx)

Use for:

- Barrier Severity Ranking
- Use Case Share

Behavior:

- left aligned labels
- right aligned numeric values
- bar track with a single filled bar
- optional rank number
- optional highlight on the first row

Recommended props:

```ts
type HorizontalBarChartProps = {
  rows: RankedBarDatum[];
  maxValue?: number;
  valueSuffix?: string;
  highlightTopRow?: boolean;
};
```

Implementation notes:

- SVG is optional here; pure HTML/CSS bars are fine
- keep max width stable so labels do not jitter
- use cyan as primary, gold only for emphasis

### 5. Grouped bar chart

Create:

- [grouped-bar-chart.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/charts/grouped-bar-chart.tsx)

Use for:

- Positioning / Message Performance

Behavior:

- one row per concept
- two series:
  - appeal
  - purchase likelihood
- horizontal grouped comparison is preferred over vertical bars

Recommended props:

```ts
type GroupedBarChartProps = {
  rows: GroupedBarDatum[];
  maxValue?: number;
};
```

Visual mapping:

- cyan = appeal
- gold = purchase likelihood

Why horizontal:

- concept labels are easier to read
- avoids cramped x-axis labels
- feels cleaner in the current card layout

### 6. Heatmap grid

Create:

- [heatmap-grid.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/charts/heatmap-grid.tsx)

Use for:

- Segment Difference Heatmap

Behavior:

- rows = key questions
- columns = segments
- each cell tinted by relative value
- numeric value remains visible in the cell

Recommended props:

```ts
type HeatmapGridProps = {
  columns: Array<{ key: string; label: string }>;
  rows: HeatmapDatum[];
  minValue?: number;
  maxValue?: number;
};
```

Implementation notes:

- CSS grid + div cells is enough
- show `n/a` clearly for nulls
- do not rely on hover-only information
- keep the color scale subtle and legible on dark background

### 7. Ladder / progression chart

Create:

- [ladder-chart.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/charts/ladder-chart.tsx)

Use for:

- Interest Funnel / Decision Ladder

Behavior:

- four named steps:
  - Feasibility
  - Category Interest
  - Price-Point Interest
  - Purchase Likelihood
- can be implemented as connected metric cards rather than a traditional funnel

Recommended props:

```ts
type LadderChartProps = {
  steps: StepDatum[];
};
```

Recommended design:

- connected horizontal or vertical step cards
- optional thin connector line
- value shown prominently
- delta between steps shown subtly if useful

### 8. Model difference chart

Create:

- [model-difference-chart.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/charts/model-difference-chart.tsx)

Use for:

- compact multi-model comparison in Insights

Behavior:

- one row per question
- show per-model values side by side
- surface spread clearly
- if fewer than 2 models, render empty state

Recommended props:

```ts
type ModelDifferenceChartProps = {
  rows: Array<{
    id: string;
    label: string;
    spread: number;
    values: Array<{ model: string; value: number }>;
  }>;
  models: string[];
};
```

Implementation notes:

- if only 2 models, dumbbell layout is a strong option
- if more than 2, stacked row of mini bars is safer

## Insights-specific data adapters

### 9. Insights chart adapters

Create:

- [insights-chart-adapters.ts](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/lib/insights-chart-adapters.ts)

Responsibility:

- convert raw `InsightsPayload` API objects into stable chart component inputs
- keep chart presentation concerns out of [insights-section.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/sections/insights-section.tsx)

Suggested exported helpers:

```ts
export function toBarrierRankingRows(payload: InsightsPayload): RankedBarDatum[]
export function toUseCaseShareRows(payload: InsightsPayload): RankedBarDatum[]
export function toMessagePerformanceRows(payload: InsightsPayload): GroupedBarDatum[]
export function toHeatmapModel(payload: InsightsPayload): {
  columns: Array<{ key: string; label: string }>;
  rows: HeatmapDatum[];
} | null
export function toInterestLadderSteps(payload: InsightsPayload): StepDatum[]
export function toModelDifferenceModel(payload: InsightsPayload): {
  models: string[];
  rows: Array<{ id: string; label: string; spread: number; values: Array<{ model: string; value: number }> }>;
} | null
```

Why this matters:

- keeps the page component clean
- protects the UI from backend payload churn
- makes unit testing much easier

## Refactor target in current Insights page

### 10. Refactor the current section

Update:

- [insights-section.tsx](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/components/sections/insights-section.tsx)

Current state:

- the current implementation already renders functional chart-like blocks inline
- this is good for proving the contract, but it should now be refactored to use the shared chart system

Refactor goals:

- remove inline chart rendering logic from the page component
- replace:
  - `HorizontalProofChart`
  - `MessagePerformanceChart`
  - `InterestLadderChart`
  - `SegmentHeatmap`
  - `ModelDifferenceChart`
- with imports from the new reusable chart directory

Keep in `insights-section.tsx`:

- section composition
- layout
- loading / empty / error state orchestration
- narrative ordering

Move out of it:

- chart drawing details
- scale calculations
- normalization logic

## Suggested implementation order

### Phase A: foundation

1. `chart-types.ts`
2. `chart-scale.ts`
3. `chart-format.ts`
4. `chart-frame.tsx`

### Phase B: first reusable charts

5. `horizontal-bar-chart.tsx`
6. `grouped-bar-chart.tsx`
7. `ladder-chart.tsx`

### Phase C: matrix / comparison charts

8. `heatmap-grid.tsx`
9. `model-difference-chart.tsx`

### Phase D: data mapping and integration

10. `insights-chart-adapters.ts`
11. refactor `insights-section.tsx`

## Acceptance criteria

The chart system is ready when:

- Barrier Ranking renders from backend rows with no inline chart code in the page
- Message Performance renders from backend rows using grouped bars
- Heatmap renders from real segment/question values
- Use Case Share uses the same horizontal bar component as barriers
- Interest Ladder uses a reusable dedicated component
- Model Difference renders a comparison visualization only when multi-model data exists
- empty states are clean and product-honest
- all charts match the premium visual system
- `npm run build` still passes

## Testing plan

### Unit-level

Add tests for:

- [insights-chart-adapters.ts](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/src/lib/insights-chart-adapters.ts)

Suggested test cases:

- missing chart payload -> returns empty/null cleanly
- barrier rows convert in descending order
- message performance rows preserve appeal vs purchase values
- heatmap model preserves columns and null values
- model difference returns null when fewer than 2 models exist

### Build verification

Run:

```bash
npm run test:unit
npm run build
```

## Backend caveats to keep visible

These are real product constraints and should stay explicit:

- concept labels are still generic (`Concept 9`, `Concept 10`, etc.) because the backend does not yet expose richer positioning titles
- trust labels remain deterministic heuristic summaries
- realism remains Neo-mode dependent and depends on realism target assets existing
- model comparison only works cleanly when multiple models were used in the run

## Optional future extension

Only after the custom chart system lands cleanly:

- consider extracting the chart system for Analysis too
- consider a small tooltip primitive if we later need denser interaction
- only evaluate a full chart library if the product expands into open-ended exploratory analytics

## Final recommendation

Implement the custom chart system now, reuse it inside Insights first, and treat it as the foundation for any later Analysis chart refinement.

This keeps the product credible, premium, and tightly matched to the current backend contract.
