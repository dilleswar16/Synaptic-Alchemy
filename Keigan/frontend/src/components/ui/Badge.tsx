import type { ComponentProps } from "react";
import { cn } from "@/utils/cn";
import { toneFillClasses, toneOnFillTextClasses, toneSoftClasses, type StatusTone } from "./toneStyles";

export interface BadgeProps extends ComponentProps<"span"> {
  tone?: StatusTone;
  /** `soft` tinted (default) or `solid` fill. */
  variant?: "soft" | "solid" | "outline";
}

/** Small counter or tag (micro 12/600): tab counts, "NEW", "×12". Not for sentences. */
export function Badge({ tone = "neutral", variant = "soft", className, ...spanProps }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 text-micro tabular-numbers",
        variant === "soft" && toneSoftClasses[tone],
        variant === "solid" && [toneFillClasses[tone], toneOnFillTextClasses[tone]],
        variant === "outline" && "border border-strong bg-surface text-muted",
        className,
      )}
      {...spanProps}
    />
  );
}
