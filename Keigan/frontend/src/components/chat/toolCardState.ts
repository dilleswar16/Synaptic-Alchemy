import type { RunStepToolView } from "@/api/askKeiganApi";
import type { LiveRunStep } from "./answerStreamReducer";

/** What a card shows as its state: the step's status, or `redacted` when the person lost access to the application the call read (spec 8.3). */
export type CardState = LiveRunStep["status"] | "redacted";

export function cardStateOf(step: LiveRunStep, tool: RunStepToolView): CardState {
  return tool.isRedacted ? "redacted" : step.status;
}

export function toolCardHeaderId(runStepId: string): string {
  return `tool-card-header-${runStepId}`;
}

export interface ToolCardOpenContext {
  /** The run has this one step and nothing else (no other call, no note). */
  isOnlyStep: boolean;
  /** "Show tool details" is on. */
  showToolDetails: boolean;
  /** The run has ended: a card does not open under the reader while its answer is still being written. */
  isRunSettled: boolean;
}

/**
 * Whether a card starts open (spec 8.3): failed and refused calls open on their own, because a problem is never hidden behind a click; a call that
 * succeeded opens when it is the only step of a finished run and "Show tool details" is on.
 */
export function isToolCardOpenByDefault(step: LiveRunStep, { isOnlyStep, showToolDetails, isRunSettled }: ToolCardOpenContext): boolean {
  if (step.status === "failed" || step.status === "refused") {
    return true;
  }
  return step.status === "succeeded" && isOnlyStep && showToolDetails && isRunSettled;
}

/** "Showing {{shown}} of {{total}}": set when the server says it cut a list to its item limit and gave both counts. */
export function toolTruncation(tool: RunStepToolView): { shown: number; total: number } | null {
  return tool.isTruncated === true && tool.itemCount !== null && tool.totalCount !== null ? { shown: tool.itemCount, total: tool.totalCount } : null;
}

/** Whether the card has a flags row: instruction-like text, masked values, simulated data or a cut list. */
export function hasToolFlags(tool: RunStepToolView): boolean {
  return tool.injectionFlagged || tool.maskedValueCount > 0 || tool.isSimulated === true || toolTruncation(tool) !== null;
}

/**
 * The line under the card's title: the problem for a call that did not run to the end, the code-written summary once it has, and while it runs
 * the stage it reported (`progressText`, null when it reported none).
 */
export function toolSummaryLine(state: CardState, tool: RunStepToolView, progressText: string | null): string | null {
  if (state === "failed" || state === "refused" || state === "skipped") {
    return tool.outcomeMessage ?? tool.summary;
  }
  return tool.summary ?? (state === "running" ? progressText : null);
}

/** The label of what a call looked at: the record when it read exactly one, otherwise the application; null when it named neither. */
export function toolTargetLabel(tool: Pick<RunStepToolView, "target">): string | null {
  const { records, applicationName } = tool.target;
  return (records.length === 1 ? records[0]?.label : applicationName) ?? null;
}
