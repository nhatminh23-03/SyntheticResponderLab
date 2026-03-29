export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function formatSectionIndex(index: number) {
  return String(index + 1).padStart(2, "0");
}
