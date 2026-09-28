import { describe, expect, it } from "vitest";

import { splitList } from "./creativeBriefLists";

describe("creative brief list fields", () => {
  it("preserves spaces inside motifs and palette entries when parsing on save", () => {
    expect(splitList("broken glass, deep roots, drifting particles")).toEqual([
      "broken glass",
      "deep roots",
      "drifting particles",
    ]);
  });

  it("accepts commas while ignoring empty entries", () => {
    expect(splitList("cyan, amber, black,")).toEqual([
      "cyan",
      "amber",
      "black",
    ]);
  });
});
