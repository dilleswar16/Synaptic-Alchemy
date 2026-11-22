import { describe, expect, it } from "vitest";
import { stepToolView, toolStep } from "./answerTestEvents";
import { cardStateOf, hasToolFlags, isToolCardOpenByDefault, toolSummaryLine, toolTargetLabel, toolTruncation } from "./toolCardState";

const settledOnly = { isOnlyStep: true, showToolDetails: true, isRunSettled: true };

describe("isToolCardOpenByDefault", () => {
  it("opens a failed or refused call on its own, whatever else is true", () => {
    const context = { isOnlyStep: false, showToolDetails: false, isRunSettled: false };
    expect(isToolCardOpenByDefault(toolStep("s", 1, { status: "failed" }), context)).toBe(true);
    expect(isToolCardOpenByDefault(toolStep("s", 1, { status: "refused" }), context)).toBe(true);
  });

  it("opens a succeeded call that is the only step of a finished run when tool details are on", () => {
    expect(isToolCardOpenByDefault(toolStep("s", 1), settledOnly)).toBe(true);
  });

  it("leaves a succeeded call closed otherwise: other steps, details off, or the run still going", () => {
    const step = toolStep("s", 1);
    expect(isToolCardOpenByDefault(step, { ...settledOnly, isOnlyStep: false })).toBe(false);
    expect(isToolCardOpenByDefault(step, { ...settledOnly, showToolDetails: false })).toBe(false);
    expect(isToolCardOpenByDefault(step, { ...settledOnly, isRunSettled: false })).toBe(false);
  });

  it("leaves a running, skipped or cancelled call closed", () => {
    for (const status of ["running", "skipped", "cancelled"] as const) {
      expect(isToolCardOpenByDefault(toolStep("s", 1, { status }), settledOnly)).toBe(false);
    }
  });
});

describe("toolTruncation and hasToolFlags", () => {
  it("shows Showing N of M from the server's own fields", () => {
    expect(toolTruncation(stepToolView({ isTruncated: true, itemCount: 20, totalCount: 134 }))).toEqual({ shown: 20, total: 134 });
  });

  it("shows nothing when the list was not cut, or a count is missing", () => {
    expect(toolTruncation(stepToolView({ isTruncated: false, itemCount: 20, totalCount: 134 }))).toBeNull();
    expect(toolTruncation(stepToolView({ isTruncated: true, itemCount: null, totalCount: 134 }))).toBeNull();
    expect(toolTruncation(stepToolView({ isTruncated: null, itemCount: null, totalCount: null }))).toBeNull();
  });

  it("does not depend on the preview, which the server cuts for large outputs", () => {
    const tool = stepToolView({ outputPreview: "{\"items\": [", isTruncated: true, itemCount: 20, totalCount: 134, isSimulated: true });
    expect(toolTruncation(tool)).toEqual({ shown: 20, total: 134 });
    expect(hasToolFlags(tool)).toBe(true);
  });

  it("has a flags row for instruction-like text, masked values, simulated data or a cut list, and not otherwise", () => {
    expect(hasToolFlags(stepToolView())).toBe(false);
    expect(hasToolFlags(stepToolView({ injectionFlagged: true }))).toBe(true);
    expect(hasToolFlags(stepToolView({ maskedValueCount: 2 }))).toBe(true);
    expect(hasToolFlags(stepToolView({ isSimulated: true }))).toBe(true);
    expect(hasToolFlags(stepToolView({ isSimulated: null }))).toBe(false);
  });
});

describe("cardStateOf, toolSummaryLine and toolTargetLabel", () => {
  it("shows the redacted state whatever the status was", () => {
    expect(cardStateOf(toolStep("s", 1), stepToolView({ isRedacted: true }))).toBe("redacted");
    expect(cardStateOf(toolStep("s", 1, { status: "failed" }), stepToolView())).toBe("failed");
  });

  it("shows the problem for a call that did not run to the end, the summary for one that did, and the progress while it runs", () => {
    const tool = stepToolView({ summary: "6 SLOs", outcomeMessage: "Could not check." });
    expect(toolSummaryLine("failed", tool, null)).toBe("Could not check.");
    expect(toolSummaryLine("succeeded", tool, null)).toBe("6 SLOs");
    expect(toolSummaryLine("running", stepToolView({ summary: null }), "Query written")).toBe("Query written");
    expect(toolSummaryLine("succeeded", stepToolView({ summary: null }), "Query written")).toBeNull();
  });

  it("names the record when the call read exactly one, the application otherwise", () => {
    const record = { kind: "incident" as const, id: "i1", label: "INC0012345", applicationId: "app-1" };
    expect(toolTargetLabel(stepToolView({ target: { applicationId: "app-1", applicationName: "Claims", records: [record] } }))).toBe("INC0012345");
    expect(toolTargetLabel(stepToolView({ target: { applicationId: "app-1", applicationName: "Claims", records: [record, record] } }))).toBe("Claims");
    expect(toolTargetLabel(stepToolView({ target: { applicationId: null, applicationName: null, records: [] } }))).toBeNull();
  });
});
