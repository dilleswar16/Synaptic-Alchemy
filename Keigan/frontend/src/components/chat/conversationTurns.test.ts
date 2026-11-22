import { describe, expect, it } from "vitest";
import type { ChatMessage } from "@/api/chatApi";
import { answerStarted } from "./answerTestEvents";
import { answerStreamReducer, initialAnswerStreamState, type LiveAnswerRun } from "./answerStreamReducer";
import { areConversationTurnsEqual, buildConversationTurns } from "./conversationTurns";

function message(messageId: string, authorRole: ChatMessage["authorRole"], messageText: string, answerRunId?: string): ChatMessage {
  return {
    messageId,
    conversationId: "conversation-1",
    authorRole,
    authorDisplayName: null,
    messageText,
    messagePayload: answerRunId ? { answerKind: "text", answerRunId } : null,
    createdAt: "2026-11-21T10:00:00Z",
  };
}

function liveRun(messageId: string, answerRunId: string): LiveAnswerRun {
  const state = answerStreamReducer(initialAnswerStreamState, {
    kind: "event",
    event: answerStarted({ answerRunId, userMessage: { messageId, messageText: "Is claims-api healthy?", createdAt: "2026-11-21T10:00:00Z" } }),
  });
  const [run] = state.runs;
  if (!run) {
    throw new Error("the event did not start a run");
  }
  return run;
}

describe("buildConversationTurns", () => {
  it("links a stored question to its run from the start, so a run that was stopped or is still going is found after a reload", () => {
    const turns = buildConversationTurns([message("q1", "user", "Question", "run-1")], [], null);
    expect(turns).toHaveLength(1);
    expect(turns[0]).toMatchObject({ key: "q1", storedAnswerRunId: "run-1", liveRun: null, isStarting: false });
  });

  it("does not draw a stored answer twice: the question already points at the run that carries the answer", () => {
    const turns = buildConversationTurns([message("q1", "user", "Question", "run-1"), message("a1", "assistant", "Answer", "run-1")], [], null);
    expect(turns).toHaveLength(1);
  });

  it("joins an answer from before runs existed to the question above it", () => {
    const turns = buildConversationTurns([message("q1", "user", "Question"), message("a1", "assistant", "Old answer")], [], null);
    expect(turns).toHaveLength(1);
    expect(turns[0]?.earlierAnswer?.messageText).toBe("Old answer");
  });

  it("lets a live run replace the stored copy of the same question, under the run id as key", () => {
    const turns = buildConversationTurns([message("q1", "user", "Question", "run-1")], [liveRun("q1", "run-1")], null);
    expect(turns).toHaveLength(1);
    expect(turns[0]).toMatchObject({ key: "run-1", storedAnswerRunId: null });
    expect(turns[0]?.liveRun?.progress.answerRunId).toBe("run-1");
  });

  it("keeps the key of a live turn the same before and after the stored conversation catches up, so it is not remounted", () => {
    const before = buildConversationTurns([], [liveRun("q1", "run-1")], null);
    const after = buildConversationTurns([message("q1", "user", "Question", "run-1")], [liveRun("q1", "run-1")], null);
    expect(before[0]?.key).toBe(after[0]?.key);
  });

  it("appends a live run that is not stored yet, and then the question still being sent", () => {
    const turns = buildConversationTurns([message("q1", "user", "First", "run-1")], [liveRun("q2", "run-2")], "Third");
    expect(turns.map((turn) => turn.question?.messageText)).toEqual(["First", "Is claims-api healthy?", "Third"]);
    expect(turns.at(-1)).toMatchObject({ key: "pending-question", isStarting: true, question: { messageId: null } });
  });
});

describe("areConversationTurnsEqual", () => {
  it("compares what a turn is made of, not the object, so a rebuilt list does not redraw an unchanged turn", () => {
    const run = liveRun("q1", "run-1");
    const first = buildConversationTurns([], [run], null)[0];
    const second = buildConversationTurns([], [run], null)[0];
    if (!first || !second) {
      throw new Error("no turn was built");
    }
    expect(first).not.toBe(second);
    expect(areConversationTurnsEqual(first, second)).toBe(true);
  });

  it("sees a run that received an event as a different turn", () => {
    const run = liveRun("q1", "run-1");
    const first = buildConversationTurns([], [run], null)[0];
    const second = buildConversationTurns([], [{ ...run, connection: "reconnecting" }], null)[0];
    if (!first || !second) {
      throw new Error("no turn was built");
    }
    expect(areConversationTurnsEqual(first, second)).toBe(false);
  });
});
