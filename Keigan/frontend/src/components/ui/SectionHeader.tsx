import type { ReactNode } from "react";
import { cn } from "@/utils/cn";

export interface SectionHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** Small uppercase label above the title. */
  eyebrow?: ReactNode;
  /** Right-aligned actions. */
  actions?: ReactNode;
  /** h2 (default, 22 px) or h3 (18 px). */
  level?: 2 | 3;
  id?: string;
  className?: string;
}

/** Heading for a page section: title, optional description and actions. */
export function SectionHeader({ title, description, eyebrow, actions, level = 2, id, className }: SectionHeaderProps) {
  const HeadingElement = level === 2 ? "h2" : "h3";
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0 flex-1">
        {eyebrow ? <p className="eyebrow mb-1">{eyebrow}</p> : null}
        <HeadingElement id={id} className={cn("font-display text-default", level === 2 ? "text-h2" : "text-h3")}>
          {title}
        </HeadingElement>
        {description ? <p className="mt-1 text-body text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
