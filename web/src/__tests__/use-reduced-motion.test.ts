import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { REDUCE_MOTION_CLASS, useReducedMotion } from "@/hooks/use-reduced-motion";

/** jsdom has no media queries; this is the smallest faithful stand-in. */
function stubMediaQuery(matches: boolean) {
  const listeners = new Set<() => void>();
  const query = {
    matches,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  vi.stubGlobal("matchMedia", () => query);
  return {
    set(next: boolean) {
      query.matches = next;
      for (const fn of listeners) fn();
    },
  };
}

describe("useReducedMotion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.classList.remove(REDUCE_MOTION_CLASS);
  });

  it("follows the OS preference as it changes", () => {
    const media = stubMediaQuery(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
    act(() => media.set(true));
    expect(result.current).toBe(true);
  });

  it("honours FiestaBoard's own Reduce motion setting", async () => {
    stubMediaQuery(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
    document.documentElement.classList.add(REDUCE_MOTION_CLASS);
    // A MutationObserver delivers on a microtask.
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBe(true);
  });
});
