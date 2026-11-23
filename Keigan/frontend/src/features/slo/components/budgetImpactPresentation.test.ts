import { describe, expect, it } from "vitest";
import { meterTone } from "./budgetImpactPresentation";

describe("meterTone", () => {
  it("is calm while well under the threshold", () => {
    expect(meterTone(5, 20)).toBe("bg-success-fill");
    expect(meterTone(14.9, 20)).toBe("bg-success-fill");
  });
  it("warns from three quarters of the threshold up to it", () => {
    expect(meterTone(15, 20)).toBe("bg-warning-fill");
    expect(meterTone(20, 20)).toBe("bg-warning-fill");
  });
  it("is danger once over the threshold", () => {
    expect(meterTone(20.1, 20)).toBe("bg-danger-fill");
  });
});
