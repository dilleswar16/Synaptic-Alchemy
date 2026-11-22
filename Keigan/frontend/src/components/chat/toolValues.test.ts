import { describe, expect, it } from "vitest";
import { asText, isHiddenField } from "./toolValues";

describe("isHiddenField", () => {
  it("hides internal identifiers and keys, which mean nothing to a person", () => {
    const record = {};
    expect(isHiddenField("id", record)).toBe(true);
    expect(isHiddenField("incident_id", record)).toBe(true);
    expect(isHiddenField("step_key", record)).toBe(true);
  });

  it("keeps a number or a name a person reads, even when it looks like a key", () => {
    expect(isHiddenField("incident_number", {})).toBe(false);
    expect(isHiddenField("application_code", {})).toBe(false);
  });

  it("hides an application's code only when its name is beside it", () => {
    expect(isHiddenField("application_code", { application_code: "CLMJP", application_name: "Claims Processing (JP)" })).toBe(true);
  });
});

describe("asText", () => {
  it("is the text of a text field and undefined for anything else", () => {
    expect(asText("A summary")).toBe("A summary");
    expect(asText(3)).toBeUndefined();
    expect(asText(null)).toBeUndefined();
  });
});
