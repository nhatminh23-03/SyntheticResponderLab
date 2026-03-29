export function formatPercent(value: number, digits = 1) {
  return `${value.toFixed(digits)}%`;
}

export function formatNumber(value: number, digits = 2) {
  return value.toFixed(digits);
}

export function truncateLabel(label: string, maxLength = 56) {
  if (label.length <= maxLength) {
    return label;
  }

  return `${label.slice(0, maxLength - 3).trimEnd()}...`;
}
