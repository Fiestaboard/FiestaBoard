import { describe, expect, it } from "vitest";

import { categoriesToRender, CATEGORY_ORDER } from "@/components/tiptap-template-editor/components/formula-categories";

/** The Insert Formula picker groups functions by the category the API reports.
 *
 * It used to render only a hardcoded list, so a function in a category added
 * server-side was invisible in the picker — no error, just a missing section. */
describe("categoriesToRender", () => {
  it("lists known categories in the picker's order, not the API's", () => {
    const grouped = { color: [1], logic: [1], array: [1] };
    expect(categoriesToRender(grouped)).toEqual(["logic", "array", "color"]);
  });

  it("includes the array and date categories", () => {
    expect(CATEGORY_ORDER).toContain("array");
    expect(CATEGORY_ORDER).toContain("date");
  });

  it("skips categories with no functions", () => {
    expect(categoriesToRender({ logic: [1], math: [], text: undefined })).toEqual(["logic"]);
  });

  it("still renders a category the API added that the UI has never heard of", () => {
    const grouped = { logic: [1], quantum: [1], alchemy: [1] };
    expect(categoriesToRender(grouped)).toEqual(["logic", "alchemy", "quantum"]);
  });

  it("returns nothing for an empty registry", () => {
    expect(categoriesToRender({})).toEqual([]);
  });
});
