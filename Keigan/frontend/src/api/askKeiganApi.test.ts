import { describe, expect, it } from "vitest";
import { answerRunPollFastIntervalMilliseconds, answerRunPollFastPollCount, answerRunPollIntervalMilliseconds, answerRunPollSlowIntervalMilliseconds, decodeAnswerEventFrame, runUnavailableReason } from "./askKeiganApi";
import { ApiError } from "./httpClient";

describe("decodeAnswerEventFrame", () => {
  it("turns a known event into an event with its type set from the frame name", () => {
    const decoded = decodeAnswerEventFrame("answer.text", JSON.stringify({ eventVersion: 1, sequence: 2, answerRunId: "run", turnNumber: 1, text: "Hello" }));
    expect(decoded).toMatchObject({ kind: "event", event: { type: "answer.text", text: "Hello", sequence: 2 } });
  });

  it("ignores an event name this client does not know, so a newer server stays compatible", () => {
    expect(decodeAnswerEventFrame("answer.something_new", JSON.stringify({ eventVersion: 1 }))).toEqual({ kind: "ignored" });
  });

  it("ignores data that is not a JSON object", () => {
    expect(decodeAnswerEventFrame("answer.text", "not json")).toEqual({ kind: "ignored" });
    expect(decodeAnswerEventFrame("answer.text", "42")).toEqual({ kind: "ignored" });
    expect(decodeAnswerEventFrame("answer.text", "null")).toEqual({ kind: "ignored" });
  });

  it("reports a frame of a newer protocol version, even when its event name is unknown", () => {
    expect(decodeAnswerEventFrame("answer.text", JSON.stringify({ eventVersion: 2 }))).toEqual({ kind: "unsupported_version" });
    expect(decodeAnswerEventFrame("future.event", JSON.stringify({ eventVersion: 3 }))).toEqual({ kind: "unsupported_version" });
  });
});

describe("answerRunPollIntervalMilliseconds", () => {
  it("polls every second at first and slows down after the fast polls", () => {
    expect(answerRunPollIntervalMilliseconds(0)).toBe(answerRunPollFastIntervalMilliseconds);
    expect(answerRunPollIntervalMilliseconds(answerRunPollFastPollCount - 1)).toBe(answerRunPollFastIntervalMilliseconds);
    expect(answerRunPollIntervalMilliseconds(answerRunPollFastPollCount)).toBe(answerRunPollSlowIntervalMilliseconds);
  });
});

describe("runUnavailableReason", () => {
  it("tells a run that is no longer shown to this person from one that is gone", () => {
    expect(runUnavailableReason(new ApiError(403, {}))).toBe("redacted");
    expect(runUnavailableReason(new ApiError(404, {}))).toBe("expired");
    expect(runUnavailableReason(new ApiError(410, {}))).toBe("expired");
  });

  it("is null for a failure that asking again may fix", () => {
    expect(runUnavailableReason(new ApiError(500, {}))).toBeNull();
    expect(runUnavailableReason(new ApiError(0, {}))).toBeNull();
    expect(runUnavailableReason(new Error("x"))).toBeNull();
  });
});
