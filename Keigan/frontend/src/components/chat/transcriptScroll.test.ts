import { describe, expect, it } from "vitest";
import { answerStarted, toolStep } from "./answerTestEvents";
import { answerStreamReducer, initialAnswerStreamState } from "./answerStreamReducer";
import { transcriptActivityKey } from "./transcriptActivity";
import { isScrolledToBottom } from "./useTranscriptScroll";

describe("transcriptActivityKey", () => {
  const started = answerStreamReducer(initialAnswerStreamState, { kind: "event", event: answerStarted() });

  it("changes when a step is added, when it finishes and when the run ends", () => {
    const keys = new Set<string>();
    keys.add(transcriptActivityKey(1, null, started.runs));
    const [run] = started.runs;
    if (!run) {
      throw new Error("no run");
    }
    const running = { ...run, progress: { ...run.progress, steps: [toolStep("s", 1, { status: "running" })] } };
    keys.add(transcriptActivityKey(1, null, [running]));
    const finished = { ...run, progress: { ...run.progress, steps: [toolStep("s", 1)] } };
    keys.add(transcriptActivityKey(1, null, [finished]));
    keys.add(transcriptActivityKey(1, null, [{ ...finished, progress: { ...finished.progress, status: "completed" } }]));
    expect(keys.size).toBe(4);
  });

  it("is the same when nothing moved the bottom", () => {
    expect(transcriptActivityKey(1, null, started.runs)).toBe(transcriptActivityKey(1, null, started.runs));
  });
});

describe("isScrolledToBottom", () => {
  it("is true within 80 pixels of the bottom and false beyond", () => {
    expect(isScrolledToBottom({ scrollHeight: 1000, scrollTop: 520, clientHeight: 400 })).toBe(true);
    expect(isScrolledToBottom({ scrollHeight: 1000, scrollTop: 519, clientHeight: 400 })).toBe(false);
    expect(isScrolledToBottom({ scrollHeight: 300, scrollTop: 0, clientHeight: 400 })).toBe(true);
  });
});
