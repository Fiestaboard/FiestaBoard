import { act, renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCloseOnBack } from "@/hooks/use-close-on-back";

/** What Back does to our entry: the browser is now on the entry below it. */
function pressBack() {
  window.history.replaceState(null, "");
  window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
}

// BB-A-12: Back (Android's gesture, the browser button) with a sheet open
// closes the sheet and stays on the screen.
describe("useCloseOnBack", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("adds a history entry while open, and Back closes instead of leaving", () => {
    const close = vi.fn();
    const before = window.history.length;
    renderHook(({ open }) => useCloseOnBack(open, close), { initialProps: { open: true } });
    expect(window.history.length).toBe(before + 1);
    act(() => pressBack());
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("takes its entry back when the sheet closes another way", () => {
    vi.useFakeTimers();
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {});
    const { rerender } = renderHook(({ open }) => useCloseOnBack(open, vi.fn()), { initialProps: { open: true } });
    rerender({ open: false });
    act(() => vi.runAllTimers());
    expect(back).toHaveBeenCalledTimes(1);
  });

  it("does nothing while closed", () => {
    const push = vi.spyOn(window.history, "pushState");
    renderHook(() => useCloseOnBack(false, vi.fn()));
    expect(push).not.toHaveBeenCalled();
  });

  // Review M1 (#2559): StrictMode runs effect → cleanup → effect on mount. The
  // sheet must stay open, with one entry and no stray Back.
  it("survives StrictMode's double effect: one entry, no Back, still open", () => {
    vi.useFakeTimers();
    const back = vi.spyOn(window.history, "back");
    const push = vi.spyOn(window.history, "pushState");
    const close = vi.fn();
    renderHook(() => useCloseOnBack(true, close), { wrapper: StrictMode });
    act(() => vi.runAllTimers());
    expect(push).toHaveBeenCalledTimes(1);
    expect(back).not.toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();
  });

  it("ignores a popstate that leaves its entry on top", () => {
    const close = vi.fn();
    renderHook(() => useCloseOnBack(true, close));
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
    });
    expect(close).not.toHaveBeenCalled();
  });
});
