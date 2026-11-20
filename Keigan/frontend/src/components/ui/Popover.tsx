import type { ReactElement, ReactNode } from "react";
import { Popover as RadixPopover } from "radix-ui";
import { cn } from "@/utils/cn";

export interface PopoverProps {
  /** The element that toggles the popover (button). */
  trigger: ReactElement;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  /** sm 240 · md 320 (default) · lg 400 · auto (content width). */
  width?: "sm" | "md" | "lg" | "auto";
  /** Remove the default 16 px padding (lists that manage their own). */
  isFlush?: boolean;
  className?: string;
  "aria-label"?: string;
}

const popoverWidths = { sm: "w-60", md: "w-80", lg: "w-[400px]", auto: "w-auto" } as const;

/** Click/focus-opened floating panel (radius 12). Closes on Esc and outside click. */
export function Popover({
  trigger,
  children,
  open,
  onOpenChange,
  side = "bottom",
  align = "center",
  width = "md",
  isFlush = false,
  className,
  ...ariaProps
}: PopoverProps) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          side={side}
          align={align}
          sideOffset={8}
          collisionPadding={12}
          aria-label={ariaProps["aria-label"]}
          className={cn(
            "z-[60] max-w-[calc(100vw-24px)] rounded-md border border-hairline bg-surface text-body text-default shadow-lg",
            "origin-[var(--radix-popover-content-transform-origin)] data-[state=closed]:animate-pop-out data-[state=open]:animate-pop-in focus-visible:outline-none",
            popoverWidths[width],
            !isFlush && "p-4",
            className,
          )}
        >
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}

/** Closes the surrounding Popover when the child is clicked. */
export const PopoverClose = RadixPopover.Close;
