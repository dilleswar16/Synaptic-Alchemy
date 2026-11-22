import { memo, useCallback, useEffect, useId, useState } from "react";
import { ChevronDown, CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { cn } from "@/utils/cn";
import { formatShortDuration } from "@/utils/formatters";
import { ToolCallCard } from "./ToolCallCard";
import type { AnswerRunProgress, ToolProgress } from "./answerStreamReducer";
import { hasTraceSteps, isOnlyStep, isTraceRedacted, traceStopReason } from "./runTraceState";
import { isToolCardOpenByDefault, toolCardHeaderId } from "./toolCardState";
import { useToolDetailsPreference } from "./useToolDetailsPreference";

/** Asks the trace to open one tool call and move focus to it (a citation `[T2]` was clicked); a new `token` is a new request for the same step. */
export interface TraceFocusRequest {
  runStepId: string;
  token: number;
}

export interface AnswerRunTraceProps {
  progress: AnswerRunProgress;
  toolProgress?: Readonly<Record<string, ToolProgress>>;
  isCompact?: boolean;
  focusRequest?: TraceFocusRequest | null;
  className?: string;
}

/** Why a run ended before it answered, in words: shown with the steps, or alone when the run had none (stopped before its first call). */
function StopReasonLine({ progress }: { progress: AnswerRunProgress }) {
  const { t } = useTranslation("chat");
  const stopReason = traceStopReason(progress);
  return stopReason ? <p className="text-caption text-muted">{t(`trace.stopped.${stopReason}`, { maximum: progress.maximumToolCalls })}</p> : null;
}

/**
 * The steps of one answer (spec 8.3): a header that collapses the section, then every tool call as a card with the model's short notes
 * between them. While the answer runs the header counts the calls against the limit; at the end it shows the total time and, when the
 * answer did not simply finish, why it stopped. Nothing renders for an answer that used no tool and is not running (a refusal), except the
 * reason it stopped when the person stopped it. When the person lost access to everything the run read, one caption replaces the steps.
 * "Show tool details" (spec 8.6) decides whether the section starts open or folded to its header; the header toggles it either way, and the
 * reason the answer stopped is shown even when the section is folded. In a compact container the cards open their details in a drawer.
 * Memoised: a run that is not the one being written does not redraw for the events of another.
 */
export const AnswerRunTrace = memo(function AnswerRunTrace({ progress, toolProgress, isCompact = false, focusRequest = null, className }: AnswerRunTraceProps) {
  const { t } = useTranslation("chat");
  const sectionId = useId();
  const { showToolDetails } = useToolDetailsPreference();
  // The switch decides the section's state again whenever it is flipped; the header toggles it in between.
  const [sectionState, setSectionState] = useState({ preference: showToolDetails, isOpen: showToolDetails });
  if (sectionState.preference !== showToolDetails) {
    setSectionState({ preference: showToolDetails, isOpen: showToolDetails });
  }
  const isSectionOpen = sectionState.isOpen;
  const setIsSectionOpen = (update: boolean | ((isOpen: boolean) => boolean)) =>
    setSectionState((previous) => ({ ...previous, isOpen: typeof update === "function" ? update(previous.isOpen) : update }));
  const [openOverrides, setOpenOverrides] = useState<Readonly<Record<string, boolean>>>({});
  const [pendingFocusStepId, setPendingFocusStepId] = useState<string | null>(null);
  const toggleCard = useCallback((runStepId: string, isOpenNow: boolean) => setOpenOverrides((previous) => ({ ...previous, [runStepId]: !isOpenNow })), []);

  useEffect(() => {
    if (focusRequest) {
      setIsSectionOpen(true);
      // A card whose details live in a drawer is only focused: opening a sheet because a citation was read would take the page away from the answer.
      if (!isCompact) {
        setOpenOverrides((previous) => ({ ...previous, [focusRequest.runStepId]: true }));
      }
      setPendingFocusStepId(focusRequest.runStepId);
    }
  }, [focusRequest, isCompact]);

  // Runs after the section and the card are open, so the header exists when it is focused.
  useEffect(() => {
    const header = pendingFocusStepId ? document.getElementById(toolCardHeaderId(pendingFocusStepId)) : null;
    if (header) {
      header.scrollIntoView({ block: "nearest" });
      header.focus({ preventScroll: true });
      setPendingFocusStepId(null);
    }
  }, [pendingFocusStepId, isSectionOpen]);

  const isRunning = progress.status === "running";
  if (!isRunning && !hasTraceSteps(progress.steps)) {
    return <StopReasonLine progress={progress} />;
  }
  if (!isRunning && isTraceRedacted(progress.steps)) {
    return <p className="text-caption text-muted">{t("trace.redacted")}</p>;
  }
  const hasProblems = progress.steps.some((step) => step.status === "failed" || step.status === "refused");
  const headerText = isRunning
    ? t("trace.working", { used: progress.toolCallCount, maximum: progress.maximumToolCalls })
    : t("trace.summary", { count: progress.toolCallCount, duration: formatShortDuration(progress.durationMilliseconds) });
  const openContext = { isOnlyStep: isOnlyStep(progress.steps), showToolDetails, isRunSettled: !isRunning };

  return (
    <section aria-label={t("trace.title")} className={cn("flex flex-col gap-2", className)}>
      <button
        type="button"
        aria-expanded={isSectionOpen}
        aria-controls={isSectionOpen ? sectionId : undefined}
        onClick={() => setIsSectionOpen((value) => !value)}
        className="flex w-full items-center gap-2 rounded-sm text-left text-caption font-medium text-muted hover:text-default"
      >
        {isRunning ? <span aria-hidden="true" className="size-2 shrink-0 animate-live-pulse rounded-full bg-brand-fill" /> : null}
        <span className="flex min-w-0 flex-1 flex-wrap gap-x-2">
          <span className="font-semibold text-default">{t("trace.title")}</span>
          <span>{headerText}</span>
        </span>
        {!isSectionOpen && hasProblems ? (
          <>
            <CircleAlert aria-hidden="true" size={14} className="shrink-0 text-danger" />
            <span className="sr-only">{t("trace.hasProblems")}</span>
          </>
        ) : null}
        <span className="shrink-0">{isSectionOpen ? t("trace.hide") : t("trace.show")}</span>
        <ChevronDown aria-hidden="true" size={14} className={cn("shrink-0 transition-transform duration-150", isSectionOpen && "rotate-180")} />
      </button>

      {isSectionOpen ? (
        <div id={sectionId} className="flex flex-col gap-2">
          <ol className="flex flex-col gap-2">
            {progress.steps.map((step) =>
              step.tool ? (
                <li key={step.runStepId} className="animate-fade-up">
                  <ToolCallCard
                    answerRunId={progress.answerRunId}
                    step={step}
                    progress={toolProgress?.[step.runStepId]}
                    isOpen={openOverrides[step.runStepId] ?? isToolCardOpenByDefault(step, openContext)}
                    onToggle={toggleCard}
                    isCompact={isCompact}
                    detailsPlacement={isCompact ? "drawer" : "card"}
                  />
                </li>
              ) : step.note ? (
                <li key={step.runStepId} className="flex animate-fade-up items-start gap-2 text-caption text-muted">
                  <KeiganLogo variant="mark" size={14} className="mt-0.5 shrink-0" />
                  <span className="min-w-0 break-words">{step.note}</span>
                </li>
              ) : null,
            )}
          </ol>
        </div>
      ) : null}
      <StopReasonLine progress={progress} />
    </section>
  );
});
