import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { formatPercentage } from "@/utils/formatters";

export type ConfidenceLevel = "low" | "moderate" | "high" | "veryHigh";

export interface ConfidenceMeterProps {
  /** 0–100. */
  percentage: number;
  /** Show "82% · High" next to the bar (default true). */
  showLabel?: boolean;
  size?: "sm" | "md";
  className?: string;
}

/** Low < 40 · Moderate < 70 · High < 90 · Very high ≥ 90. */
export function confidenceLevelFor(percentage: number): ConfidenceLevel {
  if (percentage >= 90) {
    return "veryHigh";
  }
  if (percentage >= 70) {
    return "high";
  }
  if (percentage >= 40) {
    return "moderate";
  }
  return "low";
}

/** Sweep from the action colour to the success colour across the five segments, so it follows the chosen design. */
const segmentColours = [0, 25, 50, 75, 100].map((successShare) => `color-mix(in srgb, var(--color-action) ${100 - successShare}%, var(--color-success-fill) ${successShare}%)`);

/** Five-segment confidence bar + percentage + level label (doc 04 §5). */
export function ConfidenceMeter({ percentage, showLabel = true, size = "md", className }: ConfidenceMeterProps) {
  const { t } = useTranslation("common");
  const clampedPercentage = Math.min(100, Math.max(0, percentage));
  const filledSegmentCount = clampedPercentage === 0 ? 0 : Math.max(1, Math.round(clampedPercentage / 20));
  const level = confidenceLevelFor(clampedPercentage);
  const formattedPercentage = formatPercentage(clampedPercentage, { maximumFractionDigits: 0 });
  const levelLabel = t(`confidence.${level}`);
  return (
    <div
      role="meter"
      aria-label={t("confidence.label")}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clampedPercentage)}
      aria-valuetext={t("confidence.valueText", { percentage: formattedPercentage, level: levelLabel })}
      className={cn("inline-flex items-center gap-2.5", className)}
    >
      <span aria-hidden="true" className="flex items-center gap-[3px]">
        {segmentColours.map((segmentColour, segmentIndex) => (
          <span
            key={segmentColour}
            className={cn("rounded-full", size === "md" ? "h-2 w-5" : "h-1.5 w-3.5", segmentIndex >= filledSegmentCount && "bg-surface-sunken ring-1 ring-hairline ring-inset")}
            style={segmentIndex < filledSegmentCount ? { backgroundColor: segmentColour } : undefined}
          />
        ))}
      </span>
      {showLabel ? (
        <span aria-hidden="true" className={cn("whitespace-nowrap text-default", size === "md" ? "text-body-sm" : "text-caption")}>
          <span className="font-semibold tabular-numbers">{formattedPercentage}</span>
          <span className="text-muted"> · {levelLabel}</span>
        </span>
      ) : null}
    </div>
  );
}
