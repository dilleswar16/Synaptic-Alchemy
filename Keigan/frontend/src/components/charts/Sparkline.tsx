import { useId } from "react";
import { cn } from "@/utils/cn";

export interface SparklineProps {
  values: Array<number | null>;
  /** Default 96 × 28 (doc 04 §5). */
  width?: number;
  height?: number;
  /** Dashed target line (e.g. SLO target). */
  targetValue?: number;
  /** CSS colour; defaults to Blue 1. */
  color?: string;
  /** Soft area wash under the line. */
  showArea?: boolean;
  /** Dot on the latest value. */
  showEndDot?: boolean;
  /** Fix the vertical range (otherwise min/max of values and target). */
  domain?: [number, number];
  /** Accessible description, e.g. "Availability last 24 hours, 99.95% now". Omit when decorative. */
  ariaLabel?: string;
  className?: string;
}

/** Tiny inline trend (SVG, no axes). Pair it with the number it summarises. */
export function Sparkline({
  values,
  width = 96,
  height = 28,
  targetValue,
  color = "var(--chart-1)",
  showArea = true,
  showEndDot = true,
  domain,
  ariaLabel,
  className,
}: SparklineProps) {
  const gradientId = `sparkline-${useId()}`;
  const numericValues = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (numericValues.length < 2) {
    return <svg width={width} height={height} aria-hidden={ariaLabel ? undefined : true} role={ariaLabel ? "img" : undefined} aria-label={ariaLabel} className={className} />;
  }
  const padding = 3;
  const candidateValues = targetValue !== undefined ? [...numericValues, targetValue] : numericValues;
  const minimumValue = domain?.[0] ?? Math.min(...candidateValues);
  const maximumValue = domain?.[1] ?? Math.max(...candidateValues);
  const valueRange = maximumValue - minimumValue || 1;
  const xFor = (valueIndex: number) => padding + (valueIndex / (values.length - 1)) * (width - padding * 2);
  const yFor = (value: number) => padding + (1 - (value - minimumValue) / valueRange) * (height - padding * 2);

  const points = values
    .map((value, valueIndex) => (typeof value === "number" && Number.isFinite(value) ? `${xFor(valueIndex).toFixed(1)},${yFor(value).toFixed(1)}` : null))
    .filter((point): point is string => point !== null);
  const lastIndex = values.reduce<number>((lastValidIndex, value, valueIndex) => (typeof value === "number" ? valueIndex : lastValidIndex), 0);
  const lastValue = values[lastIndex];
  const firstPoint = points[0]?.split(",");
  const lastPoint = points[points.length - 1]?.split(",");
  const areaPath =
    firstPoint && lastPoint ? `M${firstPoint[0]},${height - padding} L${points.join(" L")} L${lastPoint[0]},${height - padding} Z` : "";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : true}
      className={cn("shrink-0 overflow-visible", className)}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.18" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {targetValue !== undefined ? (
        <line x1={padding} x2={width - padding} y1={yFor(targetValue)} y2={yFor(targetValue)} stroke="var(--chart-target)" strokeWidth="1" strokeDasharray="3 3" />
      ) : null}
      {showArea && areaPath ? <path d={areaPath} fill={`url(#${gradientId})`} /> : null}
      <polyline points={points.join(" ")} fill="none" stroke={color} strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />
      {showEndDot && typeof lastValue === "number" ? (
        <circle cx={xFor(lastIndex)} cy={yFor(lastValue)} r="2.75" fill={color} stroke="var(--color-surface)" strokeWidth="1.5" />
      ) : null}
    </svg>
  );
}
