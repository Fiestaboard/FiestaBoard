import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BELOW_RAIL_QUERY, TABLET_RAIL_QUERY, useBelowRail, useTabletRailCollapse } from "@/hooks/use-below-rail";

type Listener = (event: MediaQueryListEvent) => void;

/** A matchMedia whose answers the test sets, with the listeners it was given. */
function fakeMedia(matching: Set<string>) {
  const listeners = new Map<string, Listener[]>();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: matching.has(query),
    media: query,
    addEventListener: (_: string, fn: Listener) => listeners.set(query, [...(listeners.get(query) ?? []), fn]),
    removeEventListener: (_: string, fn: Listener) =>
      listeners.set(
        query,
        (listeners.get(query) ?? []).filter((l) => l !== fn),
      ),
  }));
  return {
    change(query: string, matches: boolean) {
      if (matches) matching.add(query);
      else matching.delete(query);
      for (const fn of listeners.get(query) ?? []) fn({ matches } as MediaQueryListEvent);
    },
    listeners,
  };
}

const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

describe("useBelowRail", () => {
  it("is true below 768px and follows the viewport", () => {
    const media = fakeMedia(new Set([BELOW_RAIL_QUERY]));
    const { result } = renderHook(() => useBelowRail());
    expect(result.current).toBe(true);
    act(() => media.change(BELOW_RAIL_QUERY, false));
    expect(result.current).toBe(false);
  });
});

describe("breakpoint queries", () => {
  it("the tab bar is below 768px and the tablet band is 768–1023px (WEB-02)", () => {
    expect(BELOW_RAIL_QUERY).toBe("(max-width: 767.98px)");
    expect(TABLET_RAIL_QUERY).toBe("(min-width: 768px) and (max-width: 1023.98px)");
  });
});

describe("useTabletRailCollapse", () => {
  it("reports whether the viewport is in the band", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const { result } = renderHook(() => useTabletRailCollapse(vi.fn(), () => false));
    expect(result.current).toBe(true);
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(result.current).toBe(false);
  });

  it("brings back a stored collapsed rail on leaving the band", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const setCollapsed = vi.fn();
    renderHook(() => useTabletRailCollapse(setCollapsed, () => true));
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
  });

  it("collapses the rail, without persisting it, when the page opens between 768 and 1023px", () => {
    fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const setCollapsed = vi.fn();
    renderHook(() => useTabletRailCollapse(setCollapsed, () => false));
    expect(setCollapsed).toHaveBeenCalledWith(true, { persist: false });
  });

  it("leaves the rail alone on a wide screen", () => {
    fakeMedia(new Set());
    const setCollapsed = vi.fn();
    renderHook(() => useTabletRailCollapse(setCollapsed, () => false));
    expect(setCollapsed).not.toHaveBeenCalled();
  });

  it("restores the reader's wide-screen choice on leaving the tablet band, and collapses again on re-entering", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const setCollapsed = vi.fn();
    renderHook(() => useTabletRailCollapse(setCollapsed, () => false));
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(setCollapsed).toHaveBeenLastCalledWith(false, { persist: false });
    act(() => media.change(TABLET_RAIL_QUERY, true));
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
  });

  it("stops listening when unmounted", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const { unmount } = renderHook(() => useTabletRailCollapse(vi.fn(), () => false));
    unmount();
    expect(media.listeners.get(TABLET_RAIL_QUERY)).toEqual([]);
  });
});
