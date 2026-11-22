import { describe, expect, it } from "vitest";
import { ApiError } from "@/api/httpClient";
import { noteStep, toolStep } from "./answerTestEvents";
import { hasTraceSteps, isOnlyStep, isTraceRedacted, runUnavailableReason, traceStopReason } from "./runTraceState";

describe("run trace state", () => {
  it("says why a run stopped only when it did not simply answer or fail", () => {
    expect(traceStopReason({ stopReason: "cancelled_by_user" })).toBe("cancelled_by_user");
    expect(traceStopReason({ stopReason: "tool_limit_reached" })).toBe("tool_limit_reached");
    expect(traceStopReason({ stopReason: "answered" })).toBeNull();
    expect(traceStopReason({ stopReason: "failed" })).toBeNull();
    expect(traceStopReason({ stopReason: null })).toBeNull();
  });

  it("has steps when there is a tool call or a note", () => {
    expect(hasTraceSteps([])).toBe(false);
    expect(hasTraceSteps([noteStep("n", 1)])).toBe(true);
    expect(hasTraceSteps([toolStep("s", 1)])).toBe(true);
  });

  it("replaces the steps by one caption only when every call was redacted", () => {
    expect(isTraceRedacted([toolStep("a", 1, {}, { isRedacted: true }), toolStep("b", 2, {}, { isRedacted: true })])).toBe(true);
    expect(isTraceRedacted([toolStep("a", 1, {}, { isRedacted: true }), toolStep("b", 2)])).toBe(false);
    expect(isTraceRedacted([noteStep("n", 1)])).toBe(false);
  });

  it("counts a run of one step as having an only step", () => {
    expect(isOnlyStep([toolStep("a", 1)])).toBe(true);
    expect(isOnlyStep([noteStep("n", 1), toolStep("a", 2)])).toBe(false);
  });

  it("tells a run that is no longer shown to this person from one that is gone", () => {
    expect(runUnavailableReason(new ApiError(403, {}))).toBe("redacted");
    expect(runUnavailableReason(new ApiError(404, {}))).toBe("expired");
    expect(runUnavailableReason(new ApiError(410, {}))).toBe("expired");
    expect(runUnavailableReason(new ApiError(500, {}))).toBeNull();
    expect(runUnavailableReason(new ApiError(0, {}))).toBeNull();
    expect(runUnavailableReason(new Error("x"))).toBeNull();
  });
});
