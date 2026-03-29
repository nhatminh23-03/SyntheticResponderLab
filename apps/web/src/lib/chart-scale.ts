export function normalizeRatio(value: number, max: number) {
  if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0) {
    return 0;
  }

  return Math.max(0, Math.min(value / max, 1));
}

export function numericExtent(values: Array<number | null | undefined>) {
  const finiteValues = values.filter((value): value is number => Number.isFinite(value));
  if (finiteValues.length === 0) {
    return { min: 0, max: 0 };
  }

  return {
    min: Math.min(...finiteValues),
    max: Math.max(...finiteValues),
  };
}

export function heatmapOpacity(value: number | null, min: number, max: number) {
  if (typeof value !== "number" || !Number.isFinite(value) || max <= min) {
    return 0;
  }

  const normalized = (value - min) / (max - min);
  return Math.max(0, Math.min(normalized, 1));
}
