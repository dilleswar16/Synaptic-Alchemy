import type { ReactNode } from "react";
import { CircleCheck, Clock, TriangleExclamationPoint } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";

/** Step status derived from the backend readiness object (doc 01 §6.2). */
export type StepStatus = "not_started" | "in_progress" | "waiting" | "blocked" | "done";

export interface StepperSubStep {
  key: string;
  label: ReactNode;
  status: StepStatus;
}

export interface StepperStep {
  key: string;
  label: ReactNode;
  status: StepStatus;
  /** Short caption under the label ("Required", "3 services"). */
  description?: ReactNode;
  subSteps?: StepperSubStep[];
}

export interface StepperStage {
  key: string;
  /** Stage eyebrow: Connect, Teach, Operate, Launch. */
  label: ReactNode;
  steps: StepperStep[];
}

export interface StepperProps {
  stages: StepperStage[];
  currentStepKey?: string;
  currentSubStepKey?: string;
  onStepSelect?: (stepKey: string, subStepKey?: string) => void;
  /** Sub-steps are listed for the current step only (default) or for every step. */
  subStepVisibility?: "current" | "all";
  "aria-label": string;
  className?: string;
}

/** Hollow circle · half · clock · triangle · tick (doc 04 §5), always with a text alternative. */
export function StepStatusIcon({ status, size = 18, className }: { status: StepStatus; size?: number; className?: string }) {
  const { t } = useTranslation("common");
  const statusLabel = t(`stepStatus.${status}`);
  let icon: ReactNode;
  switch (status) {
    case "done":
      icon = <CircleCheck aria-hidden="true" size={size} strokeWidth={2} className="fill-success-fill text-surface" />;
      break;
    case "waiting":
      icon = <Clock aria-hidden="true" size={size} strokeWidth={2} className="text-info" />;
      break;
    case "blocked":
      icon = <TriangleExclamationPoint aria-hidden="true" size={size} strokeWidth={2} className="text-warning" />;
      break;
    case "in_progress":
      icon = (
        <svg aria-hidden="true" width={size} height={size} viewBox="0 0 18 18" className="text-action">
          <circle cx="9" cy="9" r="7.25" fill="none" stroke="currentColor" strokeWidth="1.75" />
          <path d="M9 3.5a5.5 5.5 0 0 1 0 11Z" fill="currentColor" />
        </svg>
      );
      break;
    default:
      icon = (
        <svg aria-hidden="true" width={size} height={size} viewBox="0 0 18 18" className="text-strong">
          <circle cx="9" cy="9" r="7.25" fill="none" stroke="currentColor" strokeWidth="1.75" />
        </svg>
      );
  }
  return (
    <span className={cn("inline-grid shrink-0 place-items-center", className)} title={statusLabel}>
      {icon}
      <span className="sr-only">{statusLabel}</span>
    </span>
  );
}

/**
 * Onboarding navigation: stages → steps → sub-steps with status icons; the current step has
 * `aria-current="step"`. Steps are buttons; navigation (deep links) is the caller's `onStepSelect`.
 */
export function Stepper({
  stages,
  currentStepKey,
  currentSubStepKey,
  onStepSelect,
  subStepVisibility = "current",
  className,
  ...ariaProps
}: StepperProps) {
  return (
    <nav aria-label={ariaProps["aria-label"]} className={cn("flex flex-col gap-5", className)}>
      {stages.map((stage) => (
        <div key={stage.key}>
          <p className="eyebrow mb-1.5 px-3">{stage.label}</p>
          <ol className="flex flex-col gap-0.5">
            {stage.steps.map((step) => {
              const isCurrent = step.key === currentStepKey;
              const showSubSteps = Boolean(step.subSteps?.length) && (subStepVisibility === "all" || isCurrent);
              return (
                <li key={step.key}>
                  <button
                    type="button"
                    aria-current={isCurrent ? "step" : undefined}
                    onClick={() => onStepSelect?.(step.key)}
                    className={cn(
                      "relative flex w-full items-start gap-2.5 rounded-sm px-3 py-2 text-left transition-colors",
                      isCurrent ? "bg-surface-selected" : "hover:bg-surface-hover",
                    )}
                  >
                    {isCurrent ? <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-gradient-brand" /> : null}
                    <StepStatusIcon status={step.status} className="mt-[3px]" />
                    <span className="min-w-0">
                      <span className={cn("block text-body", isCurrent ? "font-semibold text-heading-accent" : "font-medium text-default")}>{step.label}</span>
                      {step.description ? <span className="block text-caption text-muted">{step.description}</span> : null}
                    </span>
                  </button>
                  {showSubSteps ? (
                    <ol className="mt-0.5 mb-1 ml-[21px] flex flex-col border-l-2 border-hairline pl-3">
                      {step.subSteps?.map((subStep) => {
                        const isCurrentSubStep = isCurrent && subStep.key === currentSubStepKey;
                        return (
                          <li key={subStep.key}>
                            <button
                              type="button"
                              aria-current={isCurrentSubStep ? "step" : undefined}
                              onClick={() => onStepSelect?.(step.key, subStep.key)}
                              className={cn(
                                "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-body-sm transition-colors hover:bg-surface-hover",
                                isCurrentSubStep ? "font-semibold text-heading-accent" : "text-muted",
                              )}
                            >
                              <StepStatusIcon status={subStep.status} size={15} />
                              <span className="min-w-0 truncate">{subStep.label}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ol>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </nav>
  );
}
