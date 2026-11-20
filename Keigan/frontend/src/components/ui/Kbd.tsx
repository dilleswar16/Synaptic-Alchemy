import type { ComponentProps } from "react";
import { cn } from "@/utils/cn";

/** Keyboard key: `<Kbd>Ctrl</Kbd> <Kbd>K</Kbd>`. */
export function Kbd({ className, ...kbdProps }: ComponentProps<"kbd">) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] border border-hairline bg-surface-sunken px-1.5 font-mono text-[11px] font-medium text-muted shadow-[inset_0_-1px_0_var(--color-border)]",
        className,
      )}
      {...kbdProps}
    />
  );
}
