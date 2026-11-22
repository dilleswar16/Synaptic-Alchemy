import {
  answerRunPollIntervalMilliseconds,
  answerRunPollMaximumConsecutiveFailures,
  type AnswerRunView,
} from "@/api/askKeiganApi";
import { isApiError } from "@/api/httpClient";

/** HTTP statuses that say "ask again later" although they are client errors. */
const retryableClientStatuses: ReadonlySet<number> = new Set([408, 429]);

/** What to do with a failed read of a run's snapshot. */
export type PollFailureDecision =
  /** Wait for the next poll: the failure says nothing about the run (no connection, a server error, a rate limit). */
  | "retry"
  /** The server answered, and the answer will not change by asking again (no access, the run is gone): stop following. */
  | "run_unavailable"
  /** Too many failures in a row: stop waiting and let the person check again. */
  | "give_up";

/**
 * Decides what a failed poll means (spec 7.5). A dropped connection, a 5xx and a rate limit (an APIM 429) are retried with the usual
 * backoff, because the run goes on server-side whatever the browser sees. Any other answer from the server is final. Retrying is bounded: after
 * `answerRunPollMaximumConsecutiveFailures` failures in a row the poll gives up instead of spinning for ever.
 */
export function decidePollFailure(error: unknown, consecutiveFailureCount: number): PollFailureDecision {
  if (isApiError(error) && !error.isNetworkError && error.status < 500 && !retryableClientStatuses.has(error.status)) {
    return "run_unavailable";
  }
  return consecutiveFailureCount >= answerRunPollMaximumConsecutiveFailures ? "give_up" : "retry";
}

/** How a poll ended: the run is no longer running, it cannot be read, the poll gave up, or the caller aborted it. */
export type PollOutcome = "settled" | "run_unavailable" | "gave_up" | "aborted";

export interface PollAnswerRunOptions {
  answerRunId: string;
  signal: AbortSignal;
  fetchSnapshot: (answerRunId: string) => Promise<AnswerRunView>;
  onSnapshot: (snapshot: AnswerRunView) => void;
}

function waitUnlessAborted(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const finishWaiting = () => {
      clearTimeout(timeoutHandle);
      signal.removeEventListener("abort", finishWaiting);
      resolve();
    };
    const timeoutHandle = setTimeout(finishWaiting, milliseconds);
    signal.addEventListener("abort", finishWaiting, { once: true });
  });
}

/** Follows a run through its stored snapshot until it is no longer running; see `decidePollFailure` for what a failed read does. */
export async function pollAnswerRun({ answerRunId, signal, fetchSnapshot, onSnapshot }: PollAnswerRunOptions): Promise<PollOutcome> {
  let consecutiveFailureCount = 0;
  for (let pollCount = 0; !signal.aborted; pollCount += 1) {
    await waitUnlessAborted(answerRunPollIntervalMilliseconds(pollCount), signal);
    if (signal.aborted) {
      break;
    }
    try {
      const snapshot = await fetchSnapshot(answerRunId);
      consecutiveFailureCount = 0;
      if (signal.aborted) {
        break;
      }
      onSnapshot(snapshot);
      if (snapshot.status !== "running") {
        return "settled";
      }
    } catch (error) {
      consecutiveFailureCount += 1;
      const decision = decidePollFailure(error, consecutiveFailureCount);
      if (decision !== "retry") {
        return signal.aborted ? "aborted" : decision === "give_up" ? "gave_up" : "run_unavailable";
      }
    }
  }
  return "aborted";
}
