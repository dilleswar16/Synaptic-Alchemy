import { useId } from "react";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TraceStep } from "@/api/investigationsApi";
import { StatusChip } from "@/components/ui/StatusChip";
import { cn } from "@/utils/cn";
import { TraceAiCallView } from "./TraceAiCallView";

const statusTone = { succeeded: "success", failed: "danger", skipped: "neutral" } as const;

/** One step of the trace as a disclosure row: stage, kind, plain-words title, status and duration; expanded it shows the AI call, or the step's details (ids, codes and numbers). */
export function TraceStepRow({ step, isExpanded, onToggle, canSeeRawOutput, onShowRawOutput }: {
  step: TraceStep; isExpanded: boolean; onToggle: () => void; canSeeRawOutput: boolean; onShowRawOutput: (traceStepId: string) => void;
}) {
  const { t } = useTranslation("investigations");
  const panelId = useId();
  const title = step.aiCall ? t(`trace.feature.${step.aiCall.featureName}`, { defaultValue: step.aiCall.featureName ?? "" }) : step.stepKind === "decision" ? t(`trace.decision.${step.decisionKind}`, { defaultValue: step.decisionKind ?? "" }) : t(`trace.kind.${step.stepKind}`);
  return (
    <li className="rounded-md border border-hairline bg-surface">
      <button type="button" className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-left" aria-expanded={isExpanded} aria-controls={panelId} onClick={onToggle}>
        <ChevronRight aria-hidden="true" size={16} className={cn("shrink-0 transition-transform", isExpanded && "rotate-90")} />
        <span className="font-mono text-caption text-muted">{t("trace.steps.stepNumber", { number: step.sequenceNumber })}</span>
        <span className="text-body font-semibold text-default">{title}</span>
        <StatusChip tone={statusTone[step.stepStatus]} size="sm">{t(`trace.status.${step.stepStatus}`)}</StatusChip>
        <span className="text-caption text-muted">{t(`trace.kind.${step.stepKind}`)}</span>
        {step.durationMilliseconds !== null ? <span className="text-caption text-muted">{step.durationMilliseconds} ms</span> : null}
      </button>
      {isExpanded ? (
        <div id={panelId} className="border-t border-hairline px-4 py-3">
          {step.aiCall ? (
            <TraceAiCallView call={step.aiCall} canSeeRawOutput={canSeeRawOutput} onShowRawOutput={() => onShowRawOutput(step.traceStepId)} />
          ) : step.details ? (
            <div className="flex flex-col gap-1">
              <span className="text-caption font-semibold uppercase tracking-wide text-muted">{t("trace.details")}</span>
              <pre className="overflow-auto whitespace-pre-wrap break-words rounded-md bg-surface-sunken p-3 font-mono text-caption">{JSON.stringify(step.details, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
