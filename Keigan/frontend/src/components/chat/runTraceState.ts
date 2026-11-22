import type { AnswerStopReason } from "@/api/askKeiganApi";
import type { AnswerRunProgress, LiveRunStep } from "./answerStreamReducer";

/** The reasons a run stopped that the trace says in words: not "answered" (nothing to explain) and not "failed" (the error banner explains it). */
export type TraceStopReason = Exclude<AnswerStopReason, "answered" | "failed">;

export function traceStopReason({ stopReason }: Pick<AnswerRunProgress, "stopReason">): TraceStopReason | null {
  return stopReason === null || stopReason === "answered" || stopReason === "failed" ? null : stopReason;
}

/** Whether the run has anything to show as steps: a tool call or a note. */
export function hasTraceSteps(steps: readonly LiveRunStep[]): boolean {
  return steps.some((step) => step.tool !== null || step.note);
}

/** The person lost access to every application the run read: the steps are replaced by one caption (spec 8.5). */
export function isTraceRedacted(steps: readonly LiveRunStep[]): boolean {
  const toolSteps = steps.filter((step) => step.tool !== null);
  return toolSteps.length > 0 && toolSteps.every((step) => step.tool?.isRedacted === true);
}

/** The run is nothing but one tool call: its card opens on its own once the run is over (spec 8.3). */
export function isOnlyStep(steps: readonly LiveRunStep[]): boolean {
  return steps.length === 1;
}
