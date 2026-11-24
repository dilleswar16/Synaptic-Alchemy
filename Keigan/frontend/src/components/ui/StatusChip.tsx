import type { ComponentProps, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/utils/cn";
import { defaultToneIcons, toneFillClasses, toneSoftClasses, type StatusTone } from "./toneStyles";

export interface StatusChipProps extends Omit<ComponentProps<"span">, "children"> {
  tone?: StatusTone;
  children: ReactNode;
  /** Custom icon; `false` hides it (only when the label alone carries the meaning). Defaults to the tone icon. */
  icon?: LucideIcon | false;
  /** Show an 8 px solid dot instead of an icon. */
  dot?: boolean;
  /** Pulse the dot (live "Investigating" state). Implies `dot`. */
  pulse?: boolean;
  size?: "sm" | "md";
  /** Outline style for supporting facts (e.g. "supporting" evidence). */
  variant?: "soft" | "outline";
}

/**
 * Status pill (24 px, caption 13/500). Status is never colour alone: it always carries an icon, dot or text.
 * Tones: neutral, info, success, warning, danger, alert, ai, brand.
 */
export function StatusChip({
  tone = "neutral",
  children,
  icon,
  dot = false,
  pulse = false,
  size = "md",
  variant = "soft",
  className,
  ...spanProps
}: StatusChipProps) {
  const showDot = dot || pulse;
  const Icon = icon === false || showDot ? null : (icon ?? defaultToneIcons[tone]);
  return (
    <span
      className={cn(
        "inline-flex max-w-full shrink-0 items-center gap-1.5 rounded-full font-medium whitespace-nowrap",
        size === "md" ? "h-[var(--chip-h-md,1.5rem)] px-[var(--chip-px-md,0.625rem)] text-caption" : "h-[var(--chip-h-sm,1.25rem)] px-[var(--chip-px-sm,0.5rem)] text-micro",
        variant === "soft" ? toneSoftClasses[tone] : ["border bg-surface", toneSoftClasses[tone], "bg-transparent border-current/30"],
        className,
      )}
      {...spanProps}
    >
      {showDot ? (
        <span
          aria-hidden="true"
          className={cn("size-2 shrink-0 rounded-full text-current", toneFillClasses[tone], pulse && "animate-live-pulse")}
        />
      ) : null}
      {Icon ? <Icon aria-hidden="true" size={size === "md" ? 14 : 12} strokeWidth={2} className="shrink-0" /> : null}
      <span className="truncate">{children}</span>
    </span>
  );
}
