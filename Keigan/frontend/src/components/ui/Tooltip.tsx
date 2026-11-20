import type { ReactElement, ReactNode } from "react";
import { Tooltip as RadixTooltip } from "radix-ui";
import { cn } from "@/utils/cn";

export interface TooltipProps {
  content: ReactNode;
  /** A single focusable element (button, link). */
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  delayDuration?: number;
  /** Render the trigger without a tooltip (e.g. label already visible). */
  disabled?: boolean;
  className?: string;
}

/**
 * Dark tooltip (#1B2836, 13 px white). Opens on hover and keyboard focus. Needs the `Tooltip.Provider` that
 * `AppProviders` mounts at the root.
 */
export function Tooltip({ content, children, side = "top", align = "center", delayDuration, disabled = false, className }: TooltipProps) {
  if (disabled || content === null || content === undefined || content === "") {
    return children;
  }
  return (
    <RadixTooltip.Root delayDuration={delayDuration}>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side={side}
          align={align}
          sideOffset={6}
          collisionPadding={8}
          className={cn(
            "z-[70] max-w-xs rounded-sm bg-tooltip px-2.5 py-1.5 text-caption font-medium text-white shadow-md",
            "origin-[var(--radix-tooltip-content-transform-origin)] data-[state=closed]:animate-pop-out data-[state=delayed-open]:animate-pop-in data-[state=instant-open]:animate-pop-in",
            className,
          )}
        >
          {content}
          <RadixTooltip.Arrow className="fill-tooltip" width={10} height={5} />
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
