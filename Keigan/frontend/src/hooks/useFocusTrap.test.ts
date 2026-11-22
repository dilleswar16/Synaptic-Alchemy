import { describe, expect, it } from "vitest";
import { nextFocusTrapTarget } from "./useFocusTrap";

const first = { name: "first" };
const middle = { name: "middle" };
const last = { name: "last" };
const elements = [first, middle, last];

describe("nextFocusTrapTarget", () => {
  it("wraps Tab from the last element to the first", () => {
    expect(nextFocusTrapTarget(elements, last, false)).toBe(first);
  });

  it("wraps Shift+Tab from the first element to the last", () => {
    expect(nextFocusTrapTarget(elements, first, true)).toBe(last);
  });

  it("lets the browser move inside the list", () => {
    expect(nextFocusTrapTarget(elements, middle, false)).toBeNull();
    expect(nextFocusTrapTarget(elements, middle, true)).toBeNull();
    expect(nextFocusTrapTarget(elements, first, false)).toBeNull();
    expect(nextFocusTrapTarget(elements, last, true)).toBeNull();
  });

  it("brings focus that is outside the list back in: to the first on Tab, to the last on Shift+Tab", () => {
    const outside = { name: "outside" };
    expect(nextFocusTrapTarget(elements, outside, false)).toBe(first);
    expect(nextFocusTrapTarget(elements, outside, true)).toBe(last);
    expect(nextFocusTrapTarget(elements, null, false)).toBe(first);
  });

  it("does nothing when there is nothing to focus", () => {
    expect(nextFocusTrapTarget([], null, false)).toBeNull();
  });

  it("keeps a list of one element on that element", () => {
    expect(nextFocusTrapTarget([first], first, false)).toBe(first);
    expect(nextFocusTrapTarget([first], first, true)).toBe(first);
  });
});
