import { describe, expect, it } from "vitest";
import { parseServerSentEvents } from "./serverSentEvents";

describe("parseServerSentEvents", () => {
  it("returns a complete frame with its event name, id and data, and an empty remainder", () => {
    const { frames, remainder } = parseServerSentEvents("id: 7\nevent: tool.started\ndata: {\"a\":1}\n\n");
    expect(frames).toEqual([{ id: "7", event: "tool.started", data: "{\"a\":1}" }]);
    expect(remainder).toBe("");
  });

  it("names a frame without an event line `message`", () => {
    expect(parseServerSentEvents("data: hi\n\n").frames).toEqual([{ id: null, event: "message", data: "hi" }]);
  });

  it("keeps the text of a frame that has not ended as the remainder, and completes it with the next chunk", () => {
    const first = parseServerSentEvents("event: answer.text\ndata: par");
    expect(first.frames).toEqual([]);
    const second = parseServerSentEvents(`${first.remainder}t one\n\nevent: next\ndata: x`);
    expect(second.frames).toEqual([{ id: null, event: "answer.text", data: "part one" }]);
    expect(second.remainder).toBe("event: next\ndata: x");
  });

  it("joins several data lines with a newline", () => {
    expect(parseServerSentEvents("data: line one\ndata: line two\n\n").frames[0]?.data).toBe("line one\nline two");
  });

  it("accepts CRLF and bare CR line endings", () => {
    expect(parseServerSentEvents("event: a\r\ndata: 1\r\n\r\n").frames).toEqual([{ id: null, event: "a", data: "1" }]);
    expect(parseServerSentEvents("event: b\rdata: 2\r\rnext").frames).toEqual([{ id: null, event: "b", data: "2" }]);
  });

  it("does not split a CRLF that arrives across two chunks", () => {
    const first = parseServerSentEvents("event: a\r\ndata: 1\r\n\r");
    expect(first.frames).toEqual([]);
    const second = parseServerSentEvents(`${first.remainder}\n`);
    expect(second.frames).toEqual([{ id: null, event: "a", data: "1" }]);
    expect(second.remainder).toBe("");
  });

  it("ignores comment lines such as the keep-alive heartbeat, and blocks that carry no data", () => {
    const { frames } = parseServerSentEvents(": keep-alive\n\nevent: only-a-name\n\n: another\ndata: kept\n\n");
    expect(frames).toEqual([{ id: null, event: "message", data: "kept" }]);
  });

  it("removes one leading space of a value, and no more", () => {
    expect(parseServerSentEvents("data:  two spaces\n\n").frames[0]?.data).toBe(" two spaces");
    expect(parseServerSentEvents("data:none\n\n").frames[0]?.data).toBe("none");
  });

  it("returns several frames of one chunk in order", () => {
    const { frames } = parseServerSentEvents("event: a\ndata: 1\n\nevent: b\ndata: 2\n\n");
    expect(frames.map((frame) => frame.event)).toEqual(["a", "b"]);
  });
});
