/**
 * Chart colours (doc 04 §1.2): MetLife extended data-viz order, exposed as CSS variables so light and dark
 * themes swap automatically (`--chart-1` … `--chart-14` in tokens.css).
 *
 * Rules: assign series colours in this fixed order and keep a series' colour when filters change the series
 * count; never generate extra hues — fold the tail into "Other" (`chartOtherColor`). Status meanings use
 * `chartToneColors`, never a categorical slot.
 */
export const chartCategoricalColors: readonly string[] = Array.from({ length: 14 }, (_, slotIndex) => `var(--chart-${slotIndex + 1})`);

/** Medium gray, for an "Other" bucket. */
export const chartOtherColor = "var(--chart-10)";

/** Colour for the n-th series (0-based); anything beyond the 14 slots is "Other" gray. */
export function chartColorForIndex(seriesIndex: number): string {
  return chartCategoricalColors[seriesIndex] ?? chartOtherColor;
}

export type ChartColorToken = "danger" | "alert" | "warning" | "success" | "info" | "ai" | "neutral" | "brand" | "target" | "anomaly";

/** Status / semantic colours for charts (used by chart specifications' `colorToken`). */
export const chartToneColors: Record<ChartColorToken, string> = {
  danger: "var(--color-danger-fill)",
  alert: "var(--color-alert-fill)",
  warning: "var(--color-warning-fill)",
  success: "var(--color-success-fill)",
  info: "var(--color-info-fill)",
  ai: "var(--color-ai-fill)",
  neutral: "var(--color-neutral-fill)",
  brand: "var(--color-brand-fill)",
  target: "var(--chart-target)",
  anomaly: "var(--chart-anomaly)",
};

/** Resolves a series colour: explicit CSS colour, a token name, or the categorical slot for its index. */
export function resolveSeriesColor(color: string | undefined, seriesIndex: number): string {
  if (!color) {
    return chartColorForIndex(seriesIndex);
  }
  return color in chartToneColors ? chartToneColors[color as ChartColorToken] : color;
}

export const chartAxisTickStyle = { fontSize: 12.5, fill: "var(--chart-axis)" } as const;
export const chartGridStroke = "var(--chart-grid)";
