import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// BB-A-4 (WCAG 2.4.11): on a phone the bottom nav and the floating header are
// fixed over the page, so a focused control must scroll clear of both. The
// kit publishes their sizes on <html> (--bottom-nav-offset,
// --mobile-header-height); the page's scroll padding reads them. jsdom does no
// layout, so this holds the rule; the browser check is in the PR evidence.
const css = readFileSync(path.resolve(__dirname, "../../app/globals.css"), "utf8");
const htmlRule = css.match(/\bhtml\s*\{[^}]*scroll-padding[^}]*\}/)?.[0] ?? "";

describe("focus is never hidden under the phone chrome", () => {
  it("pads the scrollport by the bottom nav and the safe area", () => {
    expect(htmlRule).toMatch(
      /scroll-padding-bottom:\s*calc\(\s*var\(--bottom-nav-offset,\s*0px\)\s*\+\s*env\(safe-area-inset-bottom\)/,
    );
  });

  it("pads the scrollport by the floating header", () => {
    expect(htmlRule).toMatch(/scroll-padding-top:\s*calc\(\s*var\(--mobile-header-height,\s*0px\)/);
  });
});
