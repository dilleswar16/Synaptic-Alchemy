import { useId, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { ToggleGroup } from "radix-ui";
import { cn } from "@/utils/cn";

export interface SegmentedControlOption<Value extends string> {
  value: Value;
  label: ReactNode;
  icon?: LucideIcon;
  /** Hide the label visually (icon-only segment); the label is still announced. */
  isLabelHidden?: boolean;
  disabled?: boolean;
}

export interface SegmentedControlProps<Value extends string> {
  options: SegmentedControlOption<Value>[];
  value: Value;
  onValueChange: (value: Value) => void;
  /** Accessible name of the group, e.g. "View". */
  "aria-label": string;
  size?: "sm" | "md";
  className?: string;
  fullWidth?: boolean;
}

/** Pill group for small exclusive choices (Table / Board, 1h / 24h / 7d). Always has exactly one value. */
export function SegmentedControl<Value extends string>({
  options,
  value,
  onValueChange,
  size = "md",
  className,
  fullWidth = false,
  ...ariaProps
}: SegmentedControlProps<Value>) {
  const indicatorLayoutId = `segment-indicator-${useId()}`;
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(nextValue: string) => {
        if (nextValue) {
          onValueChange(nextValue as Value);
        }
      }}
      aria-label={ariaProps["aria-label"]}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-sm border border-hairline bg-surface-sunken p-0.5",
        fullWidth && "flex w-full",
        className,
      )}
    >
      {options.map((option) => {
        const isActive = option.value === value;
        const Icon = option.icon;
        return (
          <ToggleGroup.Item
            key={option.value}
            value={option.value}
            disabled={option.disabled}
            aria-label={option.isLabelHidden && typeof option.label === "string" ? option.label : undefined}
            className={cn(
              "relative inline-flex items-center justify-center gap-1.5 rounded-xs font-medium whitespace-nowrap text-muted transition-colors",
              "hover:text-default disabled:pointer-events-none disabled:opacity-50 data-[state=on]:text-default",
              size === "md" ? "h-8 px-3 text-body-sm" : "h-7 px-2.5 text-caption",
              fullWidth && "flex-1",
            )}
          >
            {isActive ? (
              <motion.span
                layoutId={indicatorLayoutId}
                aria-hidden="true"
                className="absolute inset-0 rounded-xs border border-hairline bg-surface shadow-xs"
                transition={{ type: "spring", stiffness: 520, damping: 42 }}
              />
            ) : null}
            {Icon ? <Icon aria-hidden="true" size={16} strokeWidth={1.75} className="relative" /> : null}
            {option.isLabelHidden ? null : <span className="relative">{option.label}</span>}
          </ToggleGroup.Item>
        );
      })}
    </ToggleGroup.Root>
  );
}
