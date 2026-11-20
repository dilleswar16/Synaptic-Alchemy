import { useTranslation } from "react-i18next";
import type { Priority } from "@/api/types/common";
import { cn } from "@/utils/cn";

export interface PriorityChipProps {
  priority: Priority;
  size?: "sm" | "md";
  className?: string;
}

const priorityStyles: Record<Priority, { chip: string; dot: string }> = {
  P1: { chip: "bg-danger-soft text-danger", dot: "bg-danger-fill" },
  P2: { chip: "bg-alert-soft text-alert", dot: "bg-alert-fill" },
  P3: { chip: "bg-warning-fill text-metlife-darkest-gray", dot: "bg-metlife-darkest-gray" },
  P4: { chip: "bg-neutral-soft text-neutral", dot: "bg-neutral-fill" },
};

/** P1 red · P2 berry · P3 yellow fill with dark text · P4 neutral; solid dot + label (doc 04 priority mapping). */
export function PriorityChip({ priority, size = "md", className }: PriorityChipProps) {
  const { t } = useTranslation("common");
  const styles = priorityStyles[priority];
  return (
    <span
      aria-label={t("priority.ariaLabel", { priority: priority.slice(1) })}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full font-semibold tabular-numbers",
        size === "md" ? "h-6 px-2.5 text-caption" : "h-5 px-2 text-micro",
        styles.chip,
        className,
      )}
    >
      <span aria-hidden="true" className={cn("size-2 rounded-full", styles.dot)} />
      <span aria-hidden="true">{priority}</span>
    </span>
  );
}
