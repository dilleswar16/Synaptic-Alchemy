import { isApiError } from "@/api/httpClient";

/** Why an answer could not be started, followed or stopped; the screen turns it into a message (the server's own text when it sent one). */
export interface AnswerFailure {
  errorCode: string | null;
  title: string | undefined;
  detail: string | undefined;
  correlationId: string | undefined;
  isNetworkError: boolean;
  fieldMessage: string | undefined;
  /** The run the failure is about, when "Check again" or "Stop" can still reach it. */
  answerRunId: string | undefined;
}

/** Failures the browser words itself (the server has no message for them). */
export const streamInterruptedErrorCode = "stream_interrupted";
export const unsupportedEventVersionErrorCode = "unsupported_event_version";
export const connectionLostErrorCode = "answer_connection_lost";
export const stopFailedErrorCode = "stop_failed";
export const unexpectedErrorCode = "unexpected_error";
export const toolsUnsupportedErrorCode = "ai_tools_unsupported";
export const answerInProgressErrorCode = "answer_in_progress";

export function clientFailure(errorCode: string, answerRunId?: string): AnswerFailure {
  return { errorCode, title: undefined, detail: undefined, correlationId: undefined, isNetworkError: false, fieldMessage: undefined, answerRunId };
}

/**
 * The failure an error stands for. The browser's own error text is never carried over: a rejection that is not an `ApiError` is a bug in the
 * browser, and the message for it is the catalogue's "unexpected error" wording, not the JavaScript exception (spec 4.10 rule 2).
 * A `409 answer_in_progress` keeps the id of the run that is still going, so the screen can follow or stop it.
 */
export function failureFromError(error: unknown): AnswerFailure {
  if (!isApiError(error)) {
    return clientFailure(unexpectedErrorCode);
  }
  return {
    errorCode: error.errorCode ?? null,
    title: error.title,
    detail: error.detail,
    correlationId: error.correlationId,
    isNetworkError: error.isNetworkError,
    fieldMessage: error.fieldErrors[0]?.message,
    answerRunId: error.answerRunId,
  };
}

/** The failure of a Stop that did not reach the server: its own wording, because "your question was not sent" would be false. */
export function failureFromStopError(error: unknown, answerRunId: string): AnswerFailure {
  return isApiError(error) && !error.isNetworkError ? { ...failureFromError(error), answerRunId } : clientFailure(stopFailedErrorCode, answerRunId);
}
