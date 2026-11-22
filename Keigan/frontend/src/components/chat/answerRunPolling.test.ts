import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { answerRunPollFastIntervalMilliseconds, answerRunPollMaximumConsecutiveFailures, type AnswerRunView } from "@/api/askKeiganApi";
import { ApiError } from "@/api/httpClient";
import { decidePollFailure, pollAnswerRun } from "./answerRunPolling";
import { snapshot } from "./answerTestEvents";

const networkError = new ApiError(0, {});
const serverError = new ApiError(503, { title: "Unavailable" });
const rateLimited = new ApiError(429, { title: "Too many requests" });
const forbidden = new ApiError(403, { title: "Forbidden" });
const notFound = new ApiError(404, { title: "Not found" });

describe("decidePollFailure", () => {
  it("retries a dropped connection, a server error and a rate limit", () => {
    expect(decidePollFailure(networkError, 1)).toBe("retry");
    expect(decidePollFailure(serverError, 1)).toBe("retry");
    expect(decidePollFailure(rateLimited, 1)).toBe("retry");
    expect(decidePollFailure(new ApiError(408, {}), 1)).toBe("retry");
  });

  it("retries an error that is not an API error (a bug does not strand the run)", () => {
    expect(decidePollFailure(new TypeError("boom"), 1)).toBe("retry");
  });

  it("treats an answer that will not change by asking again as final", () => {
    expect(decidePollFailure(forbidden, 1)).toBe("run_unavailable");
    expect(decidePollFailure(notFound, 1)).toBe("run_unavailable");
    expect(decidePollFailure(new ApiError(410, {}), 1)).toBe("run_unavailable");
  });

  it("gives up once the failures in a row reach the bound, and not before", () => {
    expect(decidePollFailure(serverError, answerRunPollMaximumConsecutiveFailures - 1)).toBe("retry");
    expect(decidePollFailure(serverError, answerRunPollMaximumConsecutiveFailures)).toBe("give_up");
    expect(decidePollFailure(networkError, answerRunPollMaximumConsecutiveFailures)).toBe("give_up");
  });

  it("still calls a final answer final after many failures", () => {
    expect(decidePollFailure(forbidden, answerRunPollMaximumConsecutiveFailures + 5)).toBe("run_unavailable");
  });
});

describe("pollAnswerRun", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  async function run(fetchSnapshot: (answerRunId: string) => Promise<AnswerRunView>, signal = new AbortController().signal) {
    const snapshots: AnswerRunView[] = [];
    const outcome = pollAnswerRun({ answerRunId: "run-1", signal, fetchSnapshot, onSnapshot: (value) => snapshots.push(value) });
    await vi.runAllTimersAsync();
    return { outcome: await outcome, snapshots };
  }

  it("reports every snapshot and settles when the run is no longer running", async () => {
    const results = [snapshot({ status: "running" }), snapshot({ status: "running" }), snapshot({ status: "completed" })];
    const { outcome, snapshots } = await run(() => Promise.resolve(results.shift() ?? snapshot({ status: "completed" })));
    expect(outcome).toBe("settled");
    expect(snapshots.map((value) => value.status)).toEqual(["running", "running", "completed"]);
  });

  it("is not stranded by a single server error or rate limit: it carries on and settles", async () => {
    const results: Array<AnswerRunView | ApiError> = [serverError, rateLimited, snapshot({ status: "failed" })];
    const { outcome, snapshots } = await run(() => {
      const next = results.shift();
      return next instanceof ApiError ? Promise.reject(next) : Promise.resolve(next ?? snapshot({ status: "failed" }));
    });
    expect(outcome).toBe("settled");
    expect(snapshots).toHaveLength(1);
  });

  it("stops at once when the server says the run is gone or not allowed", async () => {
    let reads = 0;
    const { outcome } = await run(() => { reads += 1; return Promise.reject(forbidden); });
    expect(outcome).toBe("run_unavailable");
    expect(reads).toBe(1);
  });

  it("gives up after the bounded number of failures in a row", async () => {
    let reads = 0;
    const { outcome } = await run(() => { reads += 1; return Promise.reject(networkError); });
    expect(outcome).toBe("gave_up");
    expect(reads).toBe(answerRunPollMaximumConsecutiveFailures);
  });

  it("counts failures in a row: a good read in between starts the count again", async () => {
    let reads = 0;
    const { outcome } = await run(() => {
      reads += 1;
      if (reads === answerRunPollMaximumConsecutiveFailures) {
        return Promise.resolve(snapshot({ status: "running" }));
      }
      return reads > answerRunPollMaximumConsecutiveFailures * 2 - 2 ? Promise.resolve(snapshot({ status: "completed" })) : Promise.reject(serverError);
    });
    expect(outcome).toBe("settled");
    expect(reads).toBeGreaterThan(answerRunPollMaximumConsecutiveFailures);
  });

  it("reads again only after the interval, and reports an abort as aborted without another read", async () => {
    const controller = new AbortController();
    let reads = 0;
    const fetchSnapshot = () => { reads += 1; return Promise.resolve(snapshot({ status: "running" })); };
    const outcome = pollAnswerRun({ answerRunId: "run-1", signal: controller.signal, fetchSnapshot, onSnapshot: () => undefined });
    await vi.advanceTimersByTimeAsync(answerRunPollFastIntervalMilliseconds - 1);
    expect(reads).toBe(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(reads).toBe(1);
    controller.abort();
    await vi.runAllTimersAsync();
    expect(await outcome).toBe("aborted");
    expect(reads).toBe(1);
  });
});
