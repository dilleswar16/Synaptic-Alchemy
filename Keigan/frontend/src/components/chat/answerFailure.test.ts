import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import { ApiError } from "@/api/httpClient";
import {
  answerInProgressErrorCode,
  clientFailure,
  connectionLostErrorCode,
  failureFromError,
  failureFromStopError,
  stopFailedErrorCode,
  streamInterruptedErrorCode,
  unexpectedErrorCode,
} from "./answerFailure";
import { describeAnswerFailure, failureActionFor } from "./answerFailureMessage";

/** A translator that returns its key, so a test sees which wording was chosen. */
const translateKey = ((key: string) => key) as unknown as TFunction;

describe("failureFromError", () => {
  it("never carries the text of a JavaScript error to the screen", () => {
    const failure = failureFromError(new TypeError("Cannot read properties of undefined"));
    expect(failure.errorCode).toBe(unexpectedErrorCode);
    expect(failure.detail).toBeUndefined();
    expect(describeAnswerFailure(failure, translateKey)).toBe("errors.unexpected");
  });

  it("keeps what the server said, with its reference and the id of the run a 409 names", () => {
    const failure = failureFromError(new ApiError(409, { errorCode: "answer_in_progress", title: "Busy", detail: "Still answering.", answerRunId: "run-9", correlationId: "corr-9" }));
    expect(failure).toMatchObject({ errorCode: "answer_in_progress", detail: "Still answering.", correlationId: "corr-9", answerRunId: "run-9", isNetworkError: false });
  });

  it("shows the server message for a server error, and the field message of a validation error first", () => {
    expect(describeAnswerFailure(failureFromError(new ApiError(503, { errorCode: "ai_unavailable", detail: "The AI model could not be reached." })), translateKey)).toBe("The AI model could not be reached.");
    expect(describeAnswerFailure(failureFromError(new ApiError(422, { errorCode: "validation_failed", detail: "Invalid.", fieldErrors: [{ field: "messageText", message: "Too long." }] })), translateKey)).toBe("Too long.");
  });

  it("words a lost connection and a missing message in the browser catalogue", () => {
    expect(describeAnswerFailure(failureFromError(new ApiError(0, { detail: "Failed to fetch" })), translateKey)).toBe("errors.connectionFailed");
    expect(describeAnswerFailure(failureFromError(new ApiError(500, {})), translateKey)).toBe("errors.generic");
    expect(describeAnswerFailure(failureFromError(new ApiError(429, { errorCode: "rate_limited" })), translateKey)).toBe("errors.rateLimited");
  });
});

describe("failureFromStopError", () => {
  it("does not say the question was not sent when only the Stop did not get through", () => {
    const failure = failureFromStopError(new ApiError(0, {}), "run-1");
    expect(failure).toMatchObject({ errorCode: stopFailedErrorCode, answerRunId: "run-1" });
    expect(describeAnswerFailure(failure, translateKey)).toBe("errors.stopFailed");
  });

  it("keeps the reason of the server when the server answered", () => {
    const failure = failureFromStopError(new ApiError(403, { errorCode: "forbidden", detail: "You cannot stop this." }), "run-1");
    expect(describeAnswerFailure(failure, translateKey)).toBe("You cannot stop this.");
  });
});

describe("failureActionFor", () => {
  it("offers to check a run again after the connection was lost", () => {
    expect(failureActionFor(clientFailure(connectionLostErrorCode, "run-1"))).toEqual({ kind: "check_again", answerRunId: "run-1" });
  });

  it("offers to stop a run that is still going, or that a Stop did not reach", () => {
    expect(failureActionFor(clientFailure(answerInProgressErrorCode, "run-2"))).toEqual({ kind: "stop", answerRunId: "run-2" });
    expect(failureActionFor(clientFailure(stopFailedErrorCode, "run-3"))).toEqual({ kind: "stop", answerRunId: "run-3" });
  });

  it("offers nothing without a run to act on, or for a failure nothing can be done about", () => {
    expect(failureActionFor(clientFailure(connectionLostErrorCode))).toBeNull();
    expect(failureActionFor(clientFailure(streamInterruptedErrorCode, "run-1"))).toBeNull();
  });
});
