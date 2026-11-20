import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCloseOnBack } from "@/hooks/use-close-on-back";

// BB-A-12: Back (Android's gesture, the browser button) with a sheet open
// closes the sheet and stays on the screen.
describe("useCloseOnBack", () => {
  afterEach(() => vi.restoreAllMocks());

  it("adds a history entry while open, and Back closes instead of leaving", () => {
    const close = vi.fn();
    const before = window.history.length;
    renderHook(({ open }) => useCloseOnBack(open, close), { initialProps: { open: true } });
    expect(window.history.length).toBe(before + 1);
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
    });
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("takes its entry back when the sheet closes another way", () => {
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {});
    const { rerender } = renderHook(({ open }) => useCloseOnBack(open, vi.fn()), { initialProps: { open: true } });
    rerender({ open: false });
    expect(back).toHaveBeenCalledTimes(1);
  });

  it("does nothing while closed", () => {
    const push = vi.spyOn(window.history, "pushState");
    renderHook(() => useCloseOnBack(false, vi.fn()));
    expect(push).not.toHaveBeenCalled();
  });
});
