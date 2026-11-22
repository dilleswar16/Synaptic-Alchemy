import type { LiveAnswerRun } from "./answerStreamReducer";

/**
 * A string that changes whenever the transcript gains or changes content that moves the bottom: a new turn, a step added, a step finished (its
 * card grows by a summary and flags), the run ending, a tool's progress line, or the streamed text growing.
 */
export function transcriptActivityKey(turnCount: number, pendingQuestion: string | null, runs: readonly LiveAnswerRun[]): string {
  const runKeys = runs.map((run) => {
    const { steps, status } = run.progress;
    return [steps.length, steps.map((step) => step.status).join(","), status, Object.keys(run.toolProgress).length, run.streamingText?.text.length ?? 0].join(":");
  });
  return [turnCount, pendingQuestion, ...runKeys].join("|");
}
