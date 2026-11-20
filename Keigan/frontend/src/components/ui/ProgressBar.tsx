import type { ReactNode } from "react";
import { cn } from "@/utils/cn";
import { formatPercentage } from "@/utils/formatters";

export type ProgressTone = "brand" | "action" | "success" | "warning" | "danger" | "ai";

export interface ProgressBarProps {
  /** 0–100. Omit for an indeterminate bar. */
  value?: number;
  tone?: ProgressTone;
  /** xs 4 px · sm 6 px (default) · md 8 px. */
  size?: "xs" | "sm" | "md";
  label?: ReactNode;
  /** Show the percentage to the right of the label. */
  showValue?: boolean;
  /** Custom value text (e.g. "21 min left"). */
  valueLabel?: ReactNode;
  className?: string;
  "aria-label"?: string;
}

const toneClasses: Record<ProgressTone, string> = {
  brand: "bg-gradient-brand",
  action: "bg-action",
  success: "bg-success-fill",
  warning: "bg-warning-fill",
  danger: "bg-danger-fill",
  ai: "bg-gradient-ai",
};

const heightClasses = { xs: "h-1", sm: "h-1.5", md: "h-2" } as const;

/** Progress with the brand gradient by default (doc 04: gradients are allowed on progress bars). */
export function ProgressBar({ value, tone = "brand", size = "sm", label, showValue = false, valueLabel, className, ...ariaProps }: ProgressBarProps) {
  const isIndeterminate = value === undefined;
  const clampedValue = isIndeterminate ? 0 : Math.min(100, Math.max(0, value));
  const valueText = valueLabel ?? (showValue && !isIndeterminate ? formatPercentage(clampedValue, { maximumFractionDigits: 0 }) : null);
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      {label || valueText ? (
        <div className="flex items-baseline justify-between gap-3 text-body-sm">
          {label ? <span className="min-w-0 truncate text-muted">{label}</span> : <span />}
          {valueText ? <span className="shrink-0 font-medium tabular-numbers text-default">{valueText}</span> : null}
        </div>
      ) : null}
      <div
        role="progressbar"
        aria-label={ariaProps["aria-label"] ?? (typeof label === "string" ? label : undefined)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={isIndeterminate ? undefined : Math.round(clampedValue)}
        className={cn("relative w-full overflow-hidden rounded-full bg-surface-sunken", heightClasses[size])}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 ease-[var(--ease-standard)]",
            toneClasses[tone],
            isIndeterminate && "absolute inset-y-0 w-1/2 animate-indeterminate",
          )}
          style={isIndeterminate ? undefined : { width: `${clampedValue}%` }}
        />
      </div>
    </div>
  );
}
