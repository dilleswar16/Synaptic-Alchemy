import type { TFunction } from "i18next";
import {
  answerInProgressErrorCode,
  connectionLostErrorCode,
  stopFailedErrorCode,
  streamInterruptedErrorCode,
  toolsUnsupportedErrorCode,
  unexpectedErrorCode,
  unsupportedEventVersionErrorCode,
  type AnswerFailure,
} from "./answerFailure";

/** Failures whose wording the browser owns: the server's text would not fit (or there is none, as when the connection broke). */
const clientWordingKeys: Readonly<Record<string, string>> = {
  [toolsUnsupportedErrorCode]: "errors.toolsUnsupported",
  [answerInProgressErrorCode]: "errors.inProgress",
  [streamInterruptedErrorCode]: "errors.streamInterrupted",
  [connectionLostErrorCode]: "errors.connectionLost",
  [stopFailedErrorCode]: "errors.stopFailed",
  [unexpectedErrorCode]: "errors.unexpected",
  [unsupportedEventVersionErrorCode]: "stream.newerVersion",
};

/** Used only when the server sent no message of its own for the code. */
const fallbackWordingKeys: Readonly<Record<string, string>> = {
  rate_limited: "errors.rateLimited",
  token_budget_exceeded: "errors.budgetExceeded",
};

/**
 * The message for a failure before or around the stream (spec 4.10). The server's message names what failed and what to do and is shown as it
 * is; the browser words only the cases it knows itself (the tools-unsupported state, a lost connection, a failed Stop, a newer protocol).
 */
export function describeAnswerFailure(failure: AnswerFailure, translate: TFunction): string {
  const errorCode = failure.errorCode ?? "";
  const clientWordingKey = clientWordingKeys[errorCode];
  if (clientWordingKey) {
    return translate(clientWordingKey);
  }
  if (failure.isNetworkError) {
    return translate("errors.connectionFailed");
  }
  return failure.fieldMessage ?? failure.detail ?? translate(fallbackWordingKeys[errorCode] ?? "errors.generic");
}

/** What the person can do about a failure, aimed at one run. */
export interface FailureAction {
  kind: "check_again" | "stop";
  answerRunId: string;
}

/** The translation key of each action's button. */
export const failureActionLabelKeys: Readonly<Record<FailureAction["kind"], string>> = {
  check_again: "errors.checkAgain",
  stop: "composer.stop",
};

/**
 * The action a failure offers: look at a run again after its connection was lost, or stop a run that is still going (another answer is
 * running in the conversation, or a Stop did not get through). Null when nothing can be done about the failure from here.
 */
export function failureActionFor(failure: AnswerFailure): FailureAction | null {
  if (failure.answerRunId === undefined) {
    return null;
  }
  switch (failure.errorCode) {
    case connectionLostErrorCode:
      return { kind: "check_again", answerRunId: failure.answerRunId };
    case answerInProgressErrorCode:
    case stopFailedErrorCode:
      return { kind: "stop", answerRunId: failure.answerRunId };
    default:
      return null;
  }
}
