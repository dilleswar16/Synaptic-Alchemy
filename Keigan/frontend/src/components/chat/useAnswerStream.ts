import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { cancelAnswerRun, fetchAnswerRun, streamAnswer } from "@/api/askKeiganApi";
import { createCorrelationId, isApiError } from "@/api/httpClient";
import {
  clientFailure,
  connectionLostErrorCode,
  failureFromError,
  failureFromStopError,
  streamInterruptedErrorCode,
  unsupportedEventVersionErrorCode,
  type AnswerFailure,
} from "./answerFailure";
import type { FailureAction } from "./answerFailureMessage";
import { pollAnswerRun } from "./answerRunPolling";
import { answerStreamReducer, initialAnswerStreamState, isRunInProgress, type StreamConnection } from "./answerStreamReducer";

export interface UseAnswerStreamOptions {
  conversationId: string;
  /** Called once an answer has ended (finished, failed, stopped or lost): refresh the stored conversation. May resolve when the refreshed conversation has arrived. */
  onSettled: () => void | Promise<void>;
}

/**
 * Asks questions in one conversation and keeps their runs: the stream fills a run event by event, Stop aborts the stream and cancels on the
 * server, and a dropped connection is recovered by polling the stored snapshot (retrying through server errors and rate limits, giving up with a
 * "Check again" action after a bounded time, and handing a run the server no longer shows to the stored conversation). Runs stay in `state.runs`
 * after they end so the cards the person was reading do not change under them; a reload shows the stored run instead.
 */
export function useAnswerStream({ conversationId, onSettled }: UseAnswerStreamOptions) {
  const [state, dispatch] = useReducer(answerStreamReducer, initialAnswerStreamState);
  const [failure, setFailure] = useState<AnswerFailure | null>(null);
  const stateReference = useRef(state);
  const controllerReference = useRef<AbortController | null>(null);
  const runIdReference = useRef<string | null>(null);
  const isStoppingReference = useRef(false);
  /** Stop was pressed before the first frame named the run: the run is cancelled as soon as it is known. */
  const isStopRequestedReference = useRef(false);
  const onSettledReference = useRef(onSettled);
  useEffect(() => {
    stateReference.current = state;
    onSettledReference.current = onSettled;
  }, [state, onSettled]);
  // The run keeps going on the server when the person leaves; only this browser stops listening.
  useEffect(() => () => controllerReference.current?.abort(), []);

  /** Follows a run by polling until it ends, then reports how: refreshes the stored conversation, or offers "Check again" when the poll gave up. */
  const followUntilSettled = useCallback(async (answerRunId: string, connection: StreamConnection, controller: AbortController) => {
    dispatch({ kind: "connection", answerRunId, connection });
    const outcome = await pollAnswerRun({ answerRunId, signal: controller.signal, fetchSnapshot: fetchAnswerRun, onSnapshot: (snapshot) => dispatch({ kind: "snapshot", snapshot }) });
    if (outcome === "aborted") {
      return; // the screen was left or a newer follow took over: this one reports nothing
    }
    if (outcome === "gave_up") {
      dispatch({ kind: "connection", answerRunId, connection: "lost" });
      setFailure(clientFailure(connectionLostErrorCode, answerRunId));
      return;
    }
    dispatch({ kind: "connection", answerRunId, connection: "closed" });
    await onSettledReference.current();
    if (outcome === "run_unavailable") {
      // The server will not show this run to this person (access removed, trace gone): the stored conversation takes over and says so.
      dispatch({ kind: "run_dropped", answerRunId });
    }
  }, []);

  const stopRun = useCallback(
    async (answerRunId: string) => {
      controllerReference.current?.abort();
      const controller = new AbortController();
      controllerReference.current = controller;
      dispatch({ kind: "connection", answerRunId, connection: "stopping" });
      let isCancelAccepted = true;
      try {
        await cancelAnswerRun(answerRunId);
      } catch (error) {
        isCancelAccepted = false;
        setFailure(failureFromStopError(error, answerRunId));
      }
      isStoppingReference.current = false;
      // Whether or not the server took the cancel, the run is followed to its real end.
      await followUntilSettled(answerRunId, isCancelAccepted ? "stopping" : "reconnecting", controller);
    },
    [followUntilSettled],
  );

  const send = useCallback(
    async (messageText: string) => {
      const controller = new AbortController();
      controllerReference.current = controller;
      runIdReference.current = null;
      isStopRequestedReference.current = false;
      setFailure(null);
      dispatch({ kind: "question_sent", messageText });
      try {
        const streamEnd = await streamAnswer(
          conversationId,
          { messageText, clientRequestId: createCorrelationId() },
          (event) => {
            runIdReference.current = event.answerRunId;
            dispatch({ kind: "event", event });
            if (isStopRequestedReference.current) {
              isStopRequestedReference.current = false;
              void stopRun(event.answerRunId);
            }
          },
          controller.signal,
        );
        const answerRunId = runIdReference.current;
        if (controller.signal.aborted) {
          return; // Stop took over: it follows the run and settles
        }
        if (streamEnd === "unsupported_event_version") {
          dispatch({ kind: "question_failed" });
          setFailure(clientFailure(unsupportedEventVersionErrorCode));
        } else if (streamEnd === "connection_ended" && answerRunId) {
          await followUntilSettled(answerRunId, "reconnecting", controller);
          return;
        } else if (streamEnd === "connection_ended") {
          dispatch({ kind: "question_failed" });
          setFailure(clientFailure(streamInterruptedErrorCode));
        } else if (answerRunId) {
          dispatch({ kind: "connection", answerRunId, connection: "closed" });
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return; // Stop took over
        }
        dispatch({ kind: "question_failed" });
        // `duplicate_request` means this question already has its answer: the refreshed conversation shows it, there is nothing to report.
        // `answer_in_progress` carries the other run's id: the refreshed conversation shows that run, and the failure offers to stop it.
        if (!(isApiError(error) && error.errorCode === "duplicate_request")) {
          setFailure(failureFromError(error));
        }
      }
      isStopRequestedReference.current = false;
      isStoppingReference.current = false;
      await onSettledReference.current();
    },
    [conversationId, followUntilSettled, stopRun],
  );

  const stop = useCallback(async () => {
    if (isStoppingReference.current) {
      return;
    }
    isStoppingReference.current = true;
    const answerRunId = runIdReference.current;
    if (answerRunId === null) {
      // Cancelling needs the run's id, which the first frame carries: aborting the request now would leave the run going on the server.
      isStopRequestedReference.current = true;
      return;
    }
    await stopRun(answerRunId);
  }, [stopRun]);

  /** The action a failure offers (`failureActionFor`): follow a run again after a lost connection, or stop one. */
  const performFailureAction = useCallback(
    async ({ kind, answerRunId }: FailureAction) => {
      setFailure(null);
      if (kind === "check_again") {
        controllerReference.current?.abort();
        const controller = new AbortController();
        controllerReference.current = controller;
        await followUntilSettled(answerRunId, "reconnecting", controller);
        return;
      }
      if (stateReference.current.runs.some((run) => run.progress.answerRunId === answerRunId)) {
        await stopRun(answerRunId);
        return;
      }
      // A run of this conversation that this browser did not start: cancel it, then the refreshed conversation shows how it ended.
      try {
        await cancelAnswerRun(answerRunId);
      } catch (error) {
        setFailure(failureFromStopError(error, answerRunId));
        return;
      }
      await onSettledReference.current();
    },
    [followUntilSettled, stopRun],
  );

  const isBusy = state.pendingQuestion !== null || state.runs.some(isRunInProgress);
  return { state, failure, isBusy, send, stop, performFailureAction };
}
