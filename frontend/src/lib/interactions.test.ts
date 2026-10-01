import { describe, expect, it } from "vitest";

import {
  exceededDragThreshold,
  isEditableTarget,
  isShortcut,
} from "./interactions";

describe("interaction helpers", () => {
  it("does not treat small pointer jitter as a drag", () => {
    expect(exceededDragThreshold(10, 10, 13, 13)).toBe(false);
    expect(exceededDragThreshold(10, 10, 15, 10)).toBe(true);
  });

  it("protects editable controls from workspace shortcuts", () => {
    expect(isEditableTarget(document.createElement("input"))).toBe(true);
    expect(isEditableTarget(document.createElement("textarea"))).toBe(true);
    expect(isEditableTarget(document.createElement("div"))).toBe(false);
  });

  it("matches shortcuts without stealing alt-modified keys", () => {
    expect(isShortcut(new KeyboardEvent("keydown", { key: "S" }), "s")).toBe(
      true,
    );
    expect(
      isShortcut(new KeyboardEvent("keydown", { key: "s", altKey: true }), "s"),
    ).toBe(false);
  });
});
