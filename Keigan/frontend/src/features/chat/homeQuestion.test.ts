import { describe, expect, it } from "vitest";
import { readHomeQuestion } from "./homeQuestion";

describe("readHomeQuestion", () => {
  it("reads the question Home put in the router state, trimmed", () => {
    expect(readHomeQuestion({ question: "  Which SLOs are at risk?  " })).toBe("Which SLOs are at risk?");
  });

  it("ignores a state without a question, a blank one and one that is not text", () => {
    expect(readHomeQuestion(null)).toBeUndefined();
    expect(readHomeQuestion(undefined)).toBeUndefined();
    expect(readHomeQuestion("question")).toBeUndefined();
    expect(readHomeQuestion({})).toBeUndefined();
    expect(readHomeQuestion({ question: "   " })).toBeUndefined();
    expect(readHomeQuestion({ question: 42 })).toBeUndefined();
  });
});
