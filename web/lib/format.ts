// Shared display formatting -- kept tiny and dependency-free.

// Whole percentages show no decimal ("80%"); anything else shows exactly
// one ("83.3%"), never Math.round/toFixed's full floating-point noise.
export function formatPercent(rate: number | null): string {
  if (rate === null) return "N/A";
  const rounded = Math.round(rate * 1000) / 10;
  return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
}
