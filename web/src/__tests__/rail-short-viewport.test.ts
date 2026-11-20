import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BELOW_RAIL_QUERY, useBelowRail, useRailBreakpoint } from "@/hooks/use-below-rail";

/** A tiny media-query evaluator for one viewport: width/height comparisons joined by "and" / ",". */
function viewport(width: number, height: number) {
  const test = (query: string) =>
    query.split(",").some((part) =>
      [...part.matchAll(/\((min|max)-(width|height):\s*([\d.]+)px\)/g)].every(([, bound, axis, value]) => {
        const actual = axis === "width" ? width : height;
        return bound === "min" ? actual >= Number(value) : actual <= Number(value);
      }),
    );
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: test(query),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
  return test;
}

// BB-A-13: a landscape phone (844×390) is wide enough for the rail, but too
// short to list every destination in it. It keeps the bottom nav instead.
describe("the rail on a short viewport", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the bottom nav on a landscape phone", () => {
    viewport(844, 390);
    expect(renderHook(() => useRailBreakpoint()).result.current).toBe("lg");
    expect(renderHook(() => useBelowRail()).result.current).toBe(true);
  });

  it("keeps the md rail on a tablet and a desktop", () => {
    viewport(820, 1180);
    expect(renderHook(() => useRailBreakpoint()).result.current).toBe("md");
    expect(renderHook(() => useBelowRail()).result.current).toBe(false);
    viewport(1440, 900);
    expect(renderHook(() => useRailBreakpoint()).result.current).toBe("md");
  });

  it("is a phone below 768px whatever the height", () => {
    const test = viewport(390, 844);
    expect(test(BELOW_RAIL_QUERY)).toBe(true);
    expect(renderHook(() => useRailBreakpoint()).result.current).toBe("md");
  });
});
