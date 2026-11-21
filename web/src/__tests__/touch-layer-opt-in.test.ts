import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// BB-A-15: FiestaUI's W2 touch layer (`coarse:` → a 44px floor on Buttons,
// Inputs, Selects, Tabs, the Fit/Actual toggle, swatches…) applies only
// inside a `.fui-coarse` ancestor. The app never opted in, so every
// default-sized control stayed 32–36px on a phone. The document root opts in;
// on a fine pointer the variant's media query keeps desktop density.
describe("the kit's touch layer", () => {
  it("is switched on for the whole document", () => {
    const root = readFileSync(path.resolve(__dirname, "../../app/root.tsx"), "utf8");
    const html = root.match(/<html lang=[^>]*>/)?.[0] ?? "";
    expect(html).toMatch(/className="[^"]*\bfui-coarse\b/);
  });
});
