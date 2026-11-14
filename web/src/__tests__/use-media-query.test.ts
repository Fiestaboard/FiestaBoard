import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useMediaQuery } from "@/hooks/use-media-query";

const original = window.matchMedia;

function mockMatchMedia(initial: boolean) {
  let matches = initial;
  const listeners = new Set<() => void>();
  window.matchMedia = vi.fn().mockImplementation((media: string) => ({
    get matches() {
      return matches;
    },
    media,
    addEventListener: (_: string, cb: () => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
  })) as unknown as typeof window.matchMedia;
  return {
    set(next: boolean) {
      matches = next;
      listeners.forEach((cb) => cb());
    },
    listeners,
  };
}

afterEach(() => {
  window.matchMedia = original;
});

describe("useMediaQuery", () => {
  it("reports the query's current match", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1280px)"));
    expect(result.current).toBe(true);
  });

  it("follows changes, and unsubscribes on unmount", () => {
    const mq = mockMatchMedia(false);
    const { result, unmount } = renderHook(() => useMediaQuery("(min-width: 1280px)"));
    expect(result.current).toBe(false);
    act(() => mq.set(true));
    expect(result.current).toBe(true);
    unmount();
    expect(mq.listeners.size).toBe(0);
  });
});
