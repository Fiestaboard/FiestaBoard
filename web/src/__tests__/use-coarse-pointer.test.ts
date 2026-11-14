import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCoarsePointer } from "@/hooks/use-coarse-pointer";

/** jsdom has no media queries; this is the smallest faithful stand-in. */
function stubPointerQuery(matches: boolean) {
  const listeners = new Set<() => void>();
  const queries: string[] = [];
  const query = {
    matches,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  vi.stubGlobal("matchMedia", (q: string) => {
    queries.push(q);
    return query;
  });
  return {
    queries,
    listeners,
    set(next: boolean) {
      query.matches = next;
      for (const fn of listeners) fn();
    },
  };
}

describe("useCoarsePointer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads the primary pointer and follows it as it changes", () => {
    const media = stubPointerQuery(false);
    const { result } = renderHook(() => useCoarsePointer());
    expect(media.queries).toContain("(pointer: coarse)");
    expect(result.current).toBe(false);
    act(() => media.set(true));
    expect(result.current).toBe(true);
  });

  it("is already true on the first render on a touch device, so a phone never paints desktop rows", () => {
    stubPointerQuery(true);
    const seen: boolean[] = [];
    renderHook(() => {
      const coarse = useCoarsePointer();
      seen.push(coarse);
      return coarse;
    });
    expect(seen[0]).toBe(true);
    expect(seen.every(Boolean)).toBe(true);
  });

  it("stops listening on unmount", () => {
    const media = stubPointerQuery(false);
    const { unmount } = renderHook(() => useCoarsePointer());
    expect(media.listeners.size).toBe(1);
    unmount();
    expect(media.listeners.size).toBe(0);
  });

  it("is false where matchMedia does not exist", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => useCoarsePointer());
    expect(result.current).toBe(false);
  });
});
