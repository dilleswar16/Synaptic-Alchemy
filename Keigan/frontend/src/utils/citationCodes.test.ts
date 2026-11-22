import { describe, expect, it } from "vitest";
import { splitCitationCodes } from "./citationCodes";

describe("splitCitationCodes", () => {
  it("returns text without a code as one text part", () => {
    expect(splitCitationCodes("No codes here.")).toEqual([{ kind: "text", text: "No codes here." }]);
  });

  it("splits at tool, evidence and runbook codes", () => {
    expect(splitCitationCodes("SLO is breached [T1] after a change [E12], see [R3].")).toEqual([
      { kind: "text", text: "SLO is breached " },
      { kind: "citation", code: "T1" },
      { kind: "text", text: " after a change " },
      { kind: "citation", code: "E12" },
      { kind: "text", text: ", see " },
      { kind: "citation", code: "R3" },
      { kind: "text", text: "." },
    ]);
  });

  it("leaves text that only looks like a code alone", () => {
    for (const text of ["[X1]", "[T]", "[T123]", "T1", "[t1]", "[E1234]", "[ T1 ]"]) {
      expect(splitCitationCodes(text)).toEqual([{ kind: "text", text }]);
    }
  });

  it("always joins back to the original text with the brackets restored", () => {
    const text = "Start [T1][T2] middle [E3] end";
    const joined = splitCitationCodes(text).map((part) => (part.kind === "text" ? part.text : `[${part.code}]`)).join("");
    expect(joined).toBe(text);
  });
});
