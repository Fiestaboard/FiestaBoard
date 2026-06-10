import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePrideActive } from "@/hooks/use-pride-active";

/**
 * `usePrideActive` is the JS-side gate for pride decorations (sidebar
 * aurora, confetti, etc.). It MUST stay in sync with the CSS gate
 * (`pride-month` class on `<html>`). Both should derive from the same
 * primary source — the calendar + the `hide_festive_months` cookie —
 * so toggling the cookie reliably hides both.
 *
 * Pre-fix the hook only read `document.documentElement.classList` on
 * mount, which meant:
 *  - If the SSR/prerender baked `pride-month` into `<html>` and the
 *    cookie was later set (and the page reloaded), the hook still
 *    returned `true` because the class was still there.
 *  - It never reacted to the class being removed at runtime.
 */
describe("usePrideActive", () => {
  const realDate = Date;

  function mockDate(iso: string) {
    const fixed = new realDate(iso).getTime();
    vi.useFakeTimers();
    vi.setSystemTime(fixed);
  }

  beforeEach(() => {
    // Reset cookies + class between tests.
    document.documentElement.className = "";
    document.cookie = "hide_festive_months=; path=/; max-age=0";
  });

  afterEach(() => {
    vi.useRealTimers();
    document.documentElement.className = "";
    document.cookie = "hide_festive_months=; path=/; max-age=0";
  });

  it("returns true in June when the hide_festive_months cookie is NOT set", () => {
    mockDate("2026-06-08T12:00:00Z");
    const { result } = renderHook(() => usePrideActive());
    expect(result.current).toBe(true);
  });

  it("returns false outside June even if pride-month class is on <html>", () => {
    mockDate("2026-07-01T12:00:00Z");
    document.documentElement.className = "pride-month";
    const { result } = renderHook(() => usePrideActive());
    expect(result.current).toBe(false);
  });

  it("returns false when hide_festive_months=true cookie is set, even if the class is still on <html>", () => {
    // Reproduces the user-visible bug: build-time prerender bakes
    // `pride-month` into the HTML, then the user opts out and reloads.
    // The class hasn't been removed yet, but the hook must respect the
    // cookie so JS-rendered decorations don't render.
    mockDate("2026-06-08T12:00:00Z");
    document.documentElement.className = "pride-month";
    document.cookie = "hide_festive_months=true; path=/";
    const { result } = renderHook(() => usePrideActive());
    expect(result.current).toBe(false);
  });
});
