import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BELOW_RAIL_QUERY, TABLET_RAIL_QUERY, useBelowRail, useRailAutoCollapse } from "@/hooks/use-below-rail";

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

describe("useRailAutoCollapse: the tablet band", () => {
  it("reports whether the viewport is in the band", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const { result } = renderHook(() => useRailAutoCollapse(vi.fn(), () => false));
    expect(result.current).toBe(true);
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(result.current).toBe(false);
  });

  it("brings back a stored collapsed rail on leaving the band", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const setCollapsed = vi.fn();
    renderHook(() => useRailAutoCollapse(setCollapsed, () => true));
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
  });

  it("collapses the rail, without persisting it, when the page opens between 768 and 1023px", () => {
    fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const setCollapsed = vi.fn();
    renderHook(() => useRailAutoCollapse(setCollapsed, () => false));
    expect(setCollapsed).toHaveBeenCalledWith(true, { persist: false });
  });

  it("leaves the rail alone on a wide screen", () => {
    fakeMedia(new Set());
    const setCollapsed = vi.fn();
    renderHook(() => useRailAutoCollapse(setCollapsed, () => false));
    expect(setCollapsed).not.toHaveBeenCalled();
  });

  it("restores the reader's wide-screen choice on leaving the tablet band, and collapses again on re-entering", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const setCollapsed = vi.fn();
    renderHook(() => useRailAutoCollapse(setCollapsed, () => false));
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(setCollapsed).toHaveBeenLastCalledWith(false, { persist: false });
    act(() => media.change(TABLET_RAIL_QUERY, true));
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
  });

  it("stops listening when unmounted", () => {
    const media = fakeMedia(new Set([TABLET_RAIL_QUERY]));
    const { unmount } = renderHook(() => useRailAutoCollapse(vi.fn(), () => false));
    unmount();
    expect(media.listeners.get(TABLET_RAIL_QUERY)).toEqual([]);
  });
});

/**
 * Owner decision D1 (BB-E-3): the editor collapses the nav to the icon rail
 * for the visit, unless it already is; leaving restores the stored (global)
 * choice. The hook never persists: an explicit toggle in the editor persists
 * through the Sidebar's own toggle, so "restore" reads the latest choice.
 */
describe("useRailAutoCollapse: D1, the page editor", () => {
  function editorHook(initial: { editor: boolean; stored?: () => boolean; band?: boolean }) {
    const media = fakeMedia(new Set(initial.band ? [TABLET_RAIL_QUERY] : []));
    const setCollapsed = vi.fn();
    const stored = vi.fn(initial.stored ?? (() => false));
    const hook = renderHook(({ editor }) => useRailAutoCollapse(setCollapsed, stored, editor), {
      initialProps: { editor: initial.editor },
    });
    return { media, setCollapsed, stored, ...hook };
  }

  it("collapses the rail, without persisting, when the editor opens on a wide screen", () => {
    const { setCollapsed, rerender } = editorHook({ editor: false });
    expect(setCollapsed).not.toHaveBeenCalled();
    rerender({ editor: true });
    expect(setCollapsed).toHaveBeenCalledTimes(1);
    expect(setCollapsed).toHaveBeenCalledWith(true, { persist: false });
  });

  it("collapses the rail when the app is opened straight on the editor", () => {
    const { setCollapsed } = editorHook({ editor: true });
    expect(setCollapsed).toHaveBeenCalledWith(true, { persist: false });
  });

  it("restores an expanded global choice on leaving the editor", () => {
    const { setCollapsed, rerender } = editorHook({ editor: false, stored: () => false });
    rerender({ editor: true });
    rerender({ editor: false });
    expect(setCollapsed).toHaveBeenLastCalledWith(false, { persist: false });
  });

  it("restores a collapsed global choice on leaving the editor", () => {
    const { setCollapsed, rerender } = editorHook({ editor: true, stored: () => true });
    rerender({ editor: false });
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
  });

  it("reads the global choice when leaving, so a toggle made in the editor is what comes back", () => {
    let stored = false;
    const { setCollapsed, rerender } = editorHook({ editor: true, stored: () => stored });
    // The reader expands, then collapses again, in the editor: the Sidebar's toggle persisted it.
    stored = true;
    rerender({ editor: false });
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
  });

  it("does nothing while the reader stays in the editor (new page to saved page, page to page)", () => {
    const { setCollapsed, rerender } = editorHook({ editor: true });
    setCollapsed.mockClear();
    rerender({ editor: true });
    rerender({ editor: true });
    expect(setCollapsed).not.toHaveBeenCalled();
  });

  it("collapses again on the next visit to the editor", () => {
    const { setCollapsed, rerender } = editorHook({ editor: false });
    rerender({ editor: true });
    rerender({ editor: false });
    rerender({ editor: true });
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
    expect(setCollapsed.mock.calls.filter(([value]) => value === true)).toHaveLength(2);
  });

  it("collapses on opening the editor even after the reader expanded the rail in the tablet band", () => {
    const { setCollapsed, rerender } = editorHook({ editor: false, band: true });
    expect(setCollapsed).toHaveBeenLastCalledWith(true, { persist: false });
    setCollapsed.mockClear();
    rerender({ editor: true });
    expect(setCollapsed).toHaveBeenCalledWith(true, { persist: false });
  });

  it("keeps the rail collapsed when the window widens out of the band inside the editor", () => {
    const { media, setCollapsed } = editorHook({ editor: true, band: true });
    setCollapsed.mockClear();
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(setCollapsed).not.toHaveBeenCalled();
  });

  it("keeps the rail collapsed when the reader leaves the editor inside the band", () => {
    const { setCollapsed, rerender } = editorHook({ editor: true, band: true });
    setCollapsed.mockClear();
    rerender({ editor: false });
    expect(setCollapsed).not.toHaveBeenCalled();
  });

  it("restores the global choice once neither the band nor the editor holds the rail", () => {
    const { media, setCollapsed, rerender } = editorHook({ editor: true, band: true, stored: () => false });
    rerender({ editor: false });
    act(() => media.change(TABLET_RAIL_QUERY, false));
    expect(setCollapsed).toHaveBeenLastCalledWith(false, { persist: false });
  });
});
