/**
 * Which glyph a FiestaPanel's code-62 flap draws. A panel is a Note-pitch
 * virtual board, so — like `resolveCode62Glyph("panel")` in @fiestaboard/ui —
 * it draws the heart whatever a Flagship preference says.
 */
import { resolveCode62Glyph as uiResolveCode62Glyph } from "@fiestaboard/ui";
import { describe, expect, it } from "vitest";

import { resolveCode62Glyph } from "@/hooks/use-board";

describe("resolveCode62Glyph — panel", () => {
  it("a panel draws the heart even with a degree preference", () => {
    expect(resolveCode62Glyph("panel", "degree")).toBe("heart");
  });

  it("agrees with the design-system package for a panel", () => {
    expect(resolveCode62Glyph("panel", "degree")).toBe(uiResolveCode62Glyph("panel", "degree"));
  });
});
