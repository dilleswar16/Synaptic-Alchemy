import { describe, expect, it } from "vitest";
import type { AnswerEvent } from "@/api/askKeiganApi";
import { answerCompleted, answerFailed, answerStarted, answerText, noteStep, snapshot, testRunId, toolFinished, toolStarted, toolStep, turnNote } from "./answerTestEvents";
import { answerStreamReducer, initialAnswerStreamState, isRunInProgress, type AnswerStreamState } from "./answerStreamReducer";

function applyEvents(...events: AnswerEvent[]): AnswerStreamState {
  return events.reduce<AnswerStreamState>((state, event) => answerStreamReducer(state, { kind: "event", event }), answerStreamReducer(initialAnswerStreamState, { kind: "question_sent", messageText: "Is claims-api healthy?" }));
}

function onlyRun(state: AnswerStreamState) {
  const [run] = state.runs;
  if (!run) {
    throw new Error("the state has no run");
  }
  return run;
}

describe("answerStreamReducer: starting a run", () => {
  it("replaces the pending question by a running run when the first frame arrives", () => {
    const state = applyEvents(answerStarted());
    expect(state.pendingQuestion).toBeNull();
    expect(onlyRun(state).progress).toMatchObject({ answerRunId: testRunId, status: "running", maximumToolCalls: 8 });
    expect(onlyRun(state).userMessage.messageText).toBe("Is claims-api healthy?");
  });

  it("keeps the pending question until a run exists, and drops it when the question fails", () => {
    const asked = answerStreamReducer(initialAnswerStreamState, { kind: "question_sent", messageText: "Q" });
    expect(asked.pendingQuestion).toBe("Q");
    expect(answerStreamReducer(asked, { kind: "question_failed" }).pendingQuestion).toBeNull();
  });

  it("ignores a repeated answer.started instead of adding a second run", () => {
    expect(applyEvents(answerStarted(), answerStarted({ sequence: 2 })).runs).toHaveLength(1);
  });
});

describe("answerStreamReducer: steps", () => {
  it("orders steps by the server's sequence number, whichever of a note and its tool arrived first", () => {
    const state = applyEvents(
      answerStarted(),
      toolStarted(2, "step-2", 2),
      turnNote(3, "step-1", 1),
    );
    expect(onlyRun(state).progress.steps.map((step) => step.runStepId)).toEqual(["step-1", "step-2"]);
  });

  it("counts a tool call that has a citation code, and fills the card when the call finishes", () => {
    const state = applyEvents(
      answerStarted(),
      toolStarted(2, "step-1", 1),
      toolFinished(3, "step-1", 1, { isSimulated: true, totalCount: 134, isTruncated: true, itemCount: 20, maskedValueCount: 3, injectionFlagged: true }),
    );
    const run = onlyRun(state);
    expect(run.progress.toolCallCount).toBe(1);
    expect(run.progress.steps[0]).toMatchObject({
      status: "succeeded",
      note: null,
      tool: { summary: "6 SLOs", isSimulated: true, totalCount: 134, isTruncated: true, itemCount: 20, maskedValueCount: 3, injectionFlagged: true },
    });
  });

  it("starts a tool step with the flags still unknown, not false", () => {
    const state = applyEvents(answerStarted(), toolStarted(2, "step-1", 1));
    expect(onlyRun(state).progress.steps[0]?.tool).toMatchObject({ isSimulated: null, totalCount: null, isTruncated: null });
  });

  it("stores a note as a step with no tool, and clears the text being streamed for that turn", () => {
    const state = applyEvents(answerStarted(), answerText(2, "Checking"), turnNote(3, "step-1", 1, "Checking first."));
    expect(onlyRun(state).progress.steps[0]).toMatchObject({ kind: "model_turn", note: "Checking first.", tool: null });
    expect(onlyRun(state).streamingText).toBeNull();
  });

  it("joins the paragraphs of one model turn and starts over for the next turn", () => {
    const sameTurn = applyEvents(answerStarted(), answerText(2, "One. "), answerText(3, "Two."));
    expect(onlyRun(sameTurn).streamingText?.text).toBe("One.\n\nTwo.");
    const nextTurn = applyEvents(answerStarted(), answerText(2, "One."), answerText(3, "Two.", 2));
    expect(onlyRun(nextTurn).streamingText).toEqual({ turnNumber: 2, text: "Two." });
  });

  it("keeps the latest progress of a step by its id", () => {
    const state = applyEvents(answerStarted(), toolStarted(2, "step-1", 1), {
      eventVersion: 1,
      sequence: 3,
      answerRunId: testRunId,
      emittedAt: "2026-11-21T10:00:01Z",
      type: "tool.progress",
      runStepId: "step-1",
      sequenceNumber: 1,
      stage: "query_generated",
      detail: { queryText: "requests | count" },
    });
    expect(onlyRun(state).toolProgress["step-1"]).toEqual({ stage: "query_generated", detail: { queryText: "requests | count" } });
  });
});

describe("answerStreamReducer: ordering and duplicates", () => {
  it("ignores an event whose sequence was already seen", () => {
    const once = applyEvents(answerStarted(), toolStarted(2, "step-1", 1));
    const twice = applyEvents(answerStarted(), toolStarted(2, "step-1", 1), toolStarted(2, "step-1", 1));
    expect(onlyRun(twice).progress.steps).toHaveLength(1);
    expect(onlyRun(twice).progress.toolCallCount).toBe(onlyRun(once).progress.toolCallCount);
  });

  it("ignores an event older than the last one", () => {
    const state = applyEvents(answerStarted(), toolStarted(5, "step-1", 1), toolStarted(3, "step-2", 2));
    expect(onlyRun(state).progress.steps.map((step) => step.runStepId)).toEqual(["step-1"]);
  });

  it("does not add a note twice", () => {
    const state = applyEvents(answerStarted(), turnNote(2, "step-1", 1), turnNote(3, "step-1", 1));
    expect(onlyRun(state).progress.steps).toHaveLength(1);
  });

  it("changes nothing for an event of a run it does not know", () => {
    const state = applyEvents(answerStarted());
    const other = answerStreamReducer(state, { kind: "event", event: { ...toolStarted(2, "step-9", 1), answerRunId: "other-run" } });
    expect(other.runs).toEqual(state.runs);
  });
});

describe("answerStreamReducer: how a run ends", () => {
  it("completes with the answer, the stop reason and the counts of the server, and clears the streamed text", () => {
    const state = applyEvents(answerStarted(), answerText(2, "Draft"), toolStarted(3, "step-1", 1), toolFinished(4, "step-1", 1), answerCompleted(5, { stopReason: "tool_limit_reached", toolCallCount: 8 }));
    const { progress, streamingText } = onlyRun(state);
    expect(progress).toMatchObject({ status: "completed", stopReason: "tool_limit_reached", toolCallCount: 8, durationMilliseconds: 900 });
    expect(progress.answer?.markdown).toBe("All healthy [T1].");
    expect(streamingText).toBeNull();
  });

  it("marks a step that was still running when the run ended as cancelled", () => {
    const state = applyEvents(answerStarted(), toolStarted(2, "step-1", 1), answerFailed(3, { stopReason: "cancelled_by_user", error: { errorCode: "cancelled", title: "Stopped", detail: "You stopped this answer.", correlationId: null, isRetryable: false, parameters: {} } }));
    const { progress } = onlyRun(state);
    expect(progress.status).toBe("cancelled");
    expect(progress.stopReason).toBe("cancelled_by_user");
    expect(progress.steps[0]?.status).toBe("cancelled");
  });

  it("ends a stopped run that never made a step as cancelled, with its reason, so the screen can say who stopped it", () => {
    const state = applyEvents(answerStarted(), answerFailed(2, { stopReason: "cancelled_by_user" }));
    expect(onlyRun(state).progress).toMatchObject({ status: "cancelled", stopReason: "cancelled_by_user", steps: [] });
  });

  it("fails with the server's problem for any other stop reason", () => {
    const state = applyEvents(answerStarted(), answerFailed(2));
    expect(onlyRun(state).progress).toMatchObject({ status: "failed", stopReason: "failed", error: { errorCode: "ai_timeout", isRetryable: true } });
  });
});

describe("answerStreamReducer: recovery by polling", () => {
  it("lets a stored snapshot replace what the events built, including the streamed text", () => {
    const running = applyEvents(answerStarted(), answerText(2, "Draft"), toolStarted(3, "step-1", 1));
    const settled = answerStreamReducer(running, {
      kind: "snapshot",
      snapshot: snapshot({ status: "completed", stopReason: "answered", steps: [toolStep("step-1", 1)], answer: answerCompleted(9).answer }),
    });
    expect(onlyRun(settled).progress.status).toBe("completed");
    expect(onlyRun(settled).progress.steps[0]?.status).toBe("succeeded");
    expect(onlyRun(settled).streamingText).toBeNull();
    expect(isRunInProgress(onlyRun(settled))).toBe(false);
  });

  it("ignores a snapshot of a run it does not hold", () => {
    const state = applyEvents(answerStarted());
    expect(answerStreamReducer(state, { kind: "snapshot", snapshot: snapshot({ answerRunId: "other" }) }).runs).toEqual(state.runs);
  });

  it("treats a run whose connection was lost as no longer in progress, and in progress again when it is followed again", () => {
    const running = applyEvents(answerStarted());
    const lost = answerStreamReducer(running, { kind: "connection", answerRunId: testRunId, connection: "lost" });
    expect(isRunInProgress(onlyRun(running))).toBe(true);
    expect(isRunInProgress(onlyRun(lost))).toBe(false);
    expect(isRunInProgress(onlyRun(answerStreamReducer(lost, { kind: "connection", answerRunId: testRunId, connection: "reconnecting" })))).toBe(true);
  });

  it("drops a run the server no longer shows", () => {
    const state = answerStreamReducer(applyEvents(answerStarted()), { kind: "run_dropped", answerRunId: testRunId });
    expect(state.runs).toEqual([]);
  });

  it("keeps a note step that came from a snapshot as it is", () => {
    const state = answerStreamReducer(applyEvents(answerStarted()), { kind: "snapshot", snapshot: snapshot({ steps: [noteStep("step-1", 1)] }) });
    expect(onlyRun(state).progress.steps[0]?.note).toBe("Checking first.");
  });
});
