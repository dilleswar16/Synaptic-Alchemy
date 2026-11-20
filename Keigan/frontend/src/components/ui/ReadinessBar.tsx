import { ArrowRight, CircleCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { ProgressBar } from "./ProgressBar";

export interface ReadinessBarProps {
  completedRequiredCount: number;
  requiredCount: number;
  /** Label of the next required step, already translated ("add an SLO"). */
  nextStepLabel?: string;
  /** Opens the full checklist. */
  onSeeAll?: () => void;
  className?: string;
}

/** Gradient progress + "6 of 8 required done · Next: …" + "See all" (doc 04 §5). */
export function ReadinessBar({ completedRequiredCount, requiredCount, nextStepLabel, onSeeAll, className }: ReadinessBarProps) {
  const { t } = useTranslation("common");
  const percentage = requiredCount === 0 ? 100 : (completedRequiredCount / requiredCount) * 100;
  const isComplete = completedRequiredCount >= requiredCount;
  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)}>
      <ProgressBar
        value={percentage}
        tone={isComplete ? "success" : "brand"}
        size="md"
        aria-label={t("readiness.summary", { completedCount: completedRequiredCount, requiredCount })}
      />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-body-sm">
        {isComplete ? <CircleCheck aria-hidden="true" size={16} strokeWidth={2} className="text-success" /> : null}
        <span className="font-medium text-default tabular-numbers">
          {isComplete ? t("readiness.allDone") : t("readiness.summary", { completedCount: completedRequiredCount, requiredCount })}
        </span>
        {!isComplete && nextStepLabel ? (
          <>
            <span aria-hidden="true" className="text-subtle">
              ·
            </span>
            <span className="text-muted">{t("readiness.next", { stepLabel: nextStepLabel })}</span>
          </>
        ) : null}
        {onSeeAll ? (
          <button
            type="button"
            onClick={onSeeAll}
            className="ml-auto inline-flex items-center gap-1 font-semibold text-action hover:text-action-hover hover:underline"
          >
            {t("readiness.seeAll")}
            <ArrowRight aria-hidden="true" size={14} strokeWidth={2} />
          </button>
        ) : null}
      </div>
    </div>
  );
}
