import { memo, useId, useState } from "react";
import { Ban, ChevronDown, ChevronRight, CircleAlert, CircleCheck, CircleDashed, CircleSlash, Lock, LoaderCircle, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/Badge";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { toneTextClasses, type StatusTone } from "@/components/ui/toneStyles";
import { cn } from "@/utils/cn";
import { formatList, formatShortDuration } from "@/utils/formatters";
import { ToolCardBody } from "./ToolCardBody";
import { ToolDetailsDrawer } from "./ToolDetailsDrawer";
import { ToolOutputDrawer } from "./ToolOutputDrawer";
import { cardStateOf, hasToolFlags, toolCardHeaderId, toolSummaryLine, toolTargetLabel, toolTruncation, type CardState } from "./toolCardState";
import { useElapsedMilliseconds } from "./useElapsedMilliseconds";
import type { LiveRunStep, ToolProgress } from "./answerStreamReducer";

/** Icon and tone per state: colour is never the only signal (spec 8.3). */
const cardStatePresentation: Record<CardState, { icon: LucideIcon; tone: StatusTone }> = {
  running: { icon: LoaderCircle, tone: "neutral" },
  succeeded: { icon: CircleCheck, tone: "success" },
  failed: { icon: CircleAlert, tone: "danger" },
  refused: { icon: Ban, tone: "warning" },
  skipped: { icon: CircleDashed, tone: "neutral" },
  cancelled: { icon: CircleSlash, tone: "neutral" },
  redacted: { icon: Lock, tone: "neutral" },
};

export interface ToolCallCardProps {
  answerRunId: string;
  /** A step of kind `tool_call`. */
  step: LiveRunStep;
  /** Latest `tool.progress` of this step, while it runs. */
  progress?: ToolProgress;
  /** Whether the body is open inside the card; ignored when the details open in a drawer. */
  isOpen: boolean;
  /** Called with this step's id and whether it is open now, so one stable callback serves every card of a run. */
  onToggle: (runStepId: string, isOpenNow: boolean) => void;
  /** Stacks label and value in the input list: the panel is too narrow for two columns. */
  isCompact?: boolean;
  /** Where the inputs and the result open: inside the card, or in a side sheet (a container too narrow for them, spec 8.2). */
  detailsPlacement?: "card" | "drawer";
}

/**
 * One tool call (spec 8.3): state, label, target, citation code, duration and a code-written summary in the header; inputs, the result
 * by presentation and the full output behind the toggle (inside the card, or in a drawer when `detailsPlacement` is "drawer"). The header is
 * the button. Its accessible name is the spec's `chat.tool.accessibleName` (label, target, state, duration of a finished call, citation); the
 * summary and the flags (instruction-like text, masked values, simulated data, a cut list) are its description, so a screen reader hears them
 * too. The running timer is left out of the name: it changes every second.
 */
export const ToolCallCard = memo(function ToolCallCard({ answerRunId, step, progress, isOpen, onToggle, isCompact = false, detailsPlacement = "card" }: ToolCallCardProps) {
  const { t } = useTranslation("chat");
  const { tool } = step;
  const [isOutputDrawerOpen, setIsOutputDrawerOpen] = useState(false);
  const [isDetailsDrawerOpen, setIsDetailsDrawerOpen] = useState(false);
  const idPrefix = useId();
  const elapsedMilliseconds = useElapsedMilliseconds(step.startedAt, step.status === "running");
  if (!tool) {
    return null;
  }

  const state = cardStateOf(step, tool);
  const { icon: StateIcon, tone } = cardStatePresentation[state];
  const isRunning = state === "running";
  const label = t(tool.labelKey, { defaultValue: tool.label });
  const targetLabel = toolTargetLabel(tool);
  const durationText = formatShortDuration(isRunning ? elapsedMilliseconds : step.durationMilliseconds);
  const stateWord = state === "refused" && tool.outcomeCode === "invalid_arguments" ? t("tool.status.invalidInput") : t(`tool.status.${state}`);
  // A finished call shows its duration; any other state shows its word first.
  const statusText = formatList([state === "succeeded" ? "" : stateWord, durationText].filter(Boolean));
  const citationLabel = tool.citationCode ? t("tool.citationLabel", { code: tool.citationCode }) : "";
  const accessibleName = t("tool.accessibleName", { label, details: formatList([targetLabel ?? "", stateWord, isRunning ? "" : durationText, citationLabel].filter(Boolean)) });
  const summaryLine = toolSummaryLine(state, tool, progress ? t(`tool.progress.${progress.stage}`, { defaultValue: "" }) || null : null);
  const truncation = toolTruncation(tool);
  const hasFlags = hasToolFlags(tool);

  const canShowFullOutput = state === "succeeded" && tool.outputCharacterCount > 0;
  const isDrawerPlacement = detailsPlacement === "drawer";
  const canOpenDetails = state !== "redacted";
  const isBodyRendered = !isDrawerPlacement && isOpen && canOpenDetails;
  const headerId = toolCardHeaderId(step.runStepId);
  const bodyId = `${idPrefix}-body`;
  const summaryId = `${idPrefix}-summary`;
  const flagsId = `${idPrefix}-flags`;
  const describedBy = [summaryLine ? summaryId : null, hasFlags ? flagsId : null].filter(Boolean).join(" ");
  const bodyProps = { answerRunId, runStepId: step.runStepId, tool, progress, isRunning, canViewFullOutput: canShowFullOutput, onViewFullOutput: () => setIsOutputDrawerOpen(true), isCompact: isCompact && !isDrawerPlacement };

  return (
    <div className="rounded-md border border-hairline bg-surface">
      <button
        type="button"
        id={headerId}
        aria-expanded={isDrawerPlacement || !canOpenDetails ? undefined : isOpen}
        aria-controls={isBodyRendered ? bodyId : undefined}
        aria-haspopup={isDrawerPlacement && canOpenDetails ? "dialog" : undefined}
        aria-label={accessibleName}
        aria-describedby={describedBy || undefined}
        onClick={isDrawerPlacement ? () => setIsDetailsDrawerOpen(true) : () => onToggle(step.runStepId, isOpen)}
        disabled={!canOpenDetails}
        className="flex w-full items-start gap-2.5 rounded-md px-3 py-2.5 text-left enabled:hover:bg-surface-hover"
      >
        <StateIcon key={state} aria-hidden="true" size={16} strokeWidth={2} className={cn("mt-0.5 shrink-0 animate-fade-in", toneTextClasses[tone], isRunning && "keigan-spinner animate-spin")} />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-body-sm font-semibold text-default">{label}</span>
            {targetLabel ? <Badge tone="brand" className="max-w-full"><span className="min-w-0 truncate">{targetLabel}</span></Badge> : null}
            {tool.citationCode ? <EvidenceChip code={tool.citationCode} /> : null}
            {statusText ? <span aria-hidden={isRunning || undefined} className="text-caption tabular-numbers text-muted">{statusText}</span> : null}
          </span>
          {summaryLine ? <span id={summaryId} className="text-caption break-words text-muted">{summaryLine}</span> : null}
          {hasFlags ? (
            <span id={flagsId} className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {tool.injectionFlagged ? <Badge tone="warning" className="h-auto max-w-full py-0.5 text-left">{t("tool.injectionFlag")}</Badge> : null}
              {tool.isSimulated === true ? <Badge tone="neutral">{t("tool.simulated")}</Badge> : null}
              {tool.maskedValueCount > 0 ? <span className="text-caption text-muted">{t("tool.masked", { count: tool.maskedValueCount })}</span> : null}
              {truncation ? <span className="text-caption text-muted">{t("tool.truncated", { shown: truncation.shown, total: truncation.total })}</span> : null}
            </span>
          ) : null}
        </span>
        {!canOpenDetails ? null : isDrawerPlacement ? (
          <ChevronRight aria-hidden="true" size={16} className="mt-0.5 shrink-0 text-muted" />
        ) : (
          <ChevronDown aria-hidden="true" size={16} className={cn("mt-0.5 shrink-0 text-muted transition-transform duration-150", isOpen && "rotate-180")} />
        )}
      </button>

      {isBodyRendered ? (
        <div id={bodyId} role="region" aria-labelledby={headerId} className="border-t border-hairline px-3 py-3">
          <ToolCardBody {...bodyProps} />
        </div>
      ) : null}

      {isDrawerPlacement && canOpenDetails ? <ToolDetailsDrawer open={isDetailsDrawerOpen} onOpenChange={setIsDetailsDrawerOpen} title={label} {...bodyProps} /> : null}

      {canShowFullOutput ? (
        <ToolOutputDrawer open={isOutputDrawerOpen} onOpenChange={setIsOutputDrawerOpen} answerRunId={answerRunId} runStepId={step.runStepId} title={label} toolName={tool.name} presentation={tool.presentation} citationCode={tool.citationCode} />
      ) : null}
    </div>
  );
});
