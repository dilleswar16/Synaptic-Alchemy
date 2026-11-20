import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";
import { cn } from "@/utils/cn";

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: ReactNode;
  /** One sentence explaining the next action. */
  description?: ReactNode;
  /** Primary action (one), e.g. a Button. */
  action?: ReactNode;
  secondaryAction?: ReactNode;
  size?: "sm" | "md" | "lg";
  /** Draw a dashed card around the state (for empty sections inside pages). */
  isBordered?: boolean;
  className?: string;
}

const illustrationSizes = { sm: "size-12", md: "size-16", lg: "size-24" } as const;
const iconSizes = { sm: 22, md: 28, lg: 40 } as const;

/** Line icon in a soft brand-gradient circle, title, one sentence and a primary action (doc 04 §5). */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  secondaryAction,
  size = "md",
  isBordered = false,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        size === "sm" ? "gap-2 px-4 py-6" : size === "md" ? "gap-3 px-6 py-12" : "gap-4 px-6 py-16",
        isBordered && "rounded-md border border-dashed border-strong",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "relative grid place-items-center rounded-full bg-gradient-brand-soft text-action ring-1 ring-action/15",
          illustrationSizes[size],
        )}
      >
        <span className="absolute inset-1.5 rounded-full bg-surface/60" />
        <Icon size={iconSizes[size]} strokeWidth={1.5} className="relative" />
      </span>
      <div className={cn("flex max-w-md flex-col", size === "sm" ? "gap-0.5" : "gap-1")}>
        <h3 className={cn("font-display text-default", size === "lg" ? "text-h2" : size === "md" ? "text-h3" : "text-h4")}>{title}</h3>
        {description ? <p className={cn("text-muted", size === "sm" ? "text-body-sm" : "text-body")}>{description}</p> : null}
      </div>
      {action || secondaryAction ? (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      ) : null}
    </div>
  );
}
