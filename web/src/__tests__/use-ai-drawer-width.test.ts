import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAiDrawerWidth } from "@/hooks/use-ai-drawer-width";
import {
  AI_DRAWER_OPEN_CLASS,
  AI_DRAWER_WIDTH_STORAGE_KEY,
  AI_DRAWER_WIDTH_VAR,
  DEFAULT_AI_DRAWER_WIDTH,
  MAX_AI_DRAWER_WIDTH,
  MIN_AI_DRAWER_WIDTH,
} from "@/lib/ai-drawer-width";

const VIEWPORT = 1600; // 40% = 640px of headroom

const reservation = () => document.documentElement.style.getPropertyValue(AI_DRAWER_WIDTH_VAR);

beforeEach(() => {
  window.innerWidth = VIEWPORT;
  localStorage.clear();
  document.documentElement.removeAttribute("style");
  document.documentElement.className = "";
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useAiDrawerWidth", () => {
  it("opens at the default width when the viewer has never resized it", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(result.current.width).toBe(DEFAULT_AI_DRAWER_WIDTH);
  });

  it("publishes the width for the page's reservation to follow", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(reservation()).toBe(`${DEFAULT_AI_DRAWER_WIDTH}px`);

    act(() => result.current.setWidth(520));
    expect(reservation()).toBe("520px");
  });

  it("remembers a chosen width for the next visit", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    act(() => result.current.setWidth(512));
    expect(localStorage.getItem(AI_DRAWER_WIDTH_STORAGE_KEY)).toBe("512");
  });

  it("opens at the width this viewer chose last time", () => {
    localStorage.setItem(AI_DRAWER_WIDTH_STORAGE_KEY, "512");
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(result.current.width).toBe(512);
  });

  it("falls back to the default when storage holds junk", () => {
    localStorage.setItem(AI_DRAWER_WIDTH_STORAGE_KEY, "¯\\_(ツ)_/¯");
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(result.current.width).toBe(DEFAULT_AI_DRAWER_WIDTH);
  });

  it("falls back to the default when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(result.current.width).toBe(DEFAULT_AI_DRAWER_WIDTH);
  });

  it("brings a stored width that is too wide for this screen inside the clamp", () => {
    localStorage.setItem(AI_DRAWER_WIDTH_STORAGE_KEY, "1200");
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(result.current.width).toBe(640); // 40% of 1600
  });

  it("clamps a requested width at both ends", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    act(() => result.current.setWidth(10));
    expect(result.current.width).toBe(MIN_AI_DRAWER_WIDTH);

    act(() => result.current.setWidth(5000));
    expect(result.current.width).toBe(640);
  });

  it("reports the ceiling this viewport allows, for the separator to publish", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(result.current.maxWidth).toBe(640);
    expect(result.current.minWidth).toBe(MIN_AI_DRAWER_WIDTH);
    expect(MAX_AI_DRAWER_WIDTH).toBeGreaterThan(640);
  });

  it("toggles from the default out to the widest, and back again", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    act(() => result.current.toggleWidth());
    expect(result.current.width).toBe(640);

    act(() => result.current.toggleWidth());
    expect(result.current.width).toBe(DEFAULT_AI_DRAWER_WIDTH);
  });

  it("toggles back to the width the viewer last chose, not the maximum", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    act(() => result.current.setWidth(480));
    act(() => result.current.toggleWidth());
    expect(result.current.width).toBe(DEFAULT_AI_DRAWER_WIDTH);

    act(() => result.current.toggleWidth());
    expect(result.current.width).toBe(480);
  });

  it("resets to the default", () => {
    const { result } = renderHook(() => useAiDrawerWidth(true));
    act(() => result.current.setWidth(600));
    act(() => result.current.resetWidth());
    expect(result.current.width).toBe(DEFAULT_AI_DRAWER_WIDTH);
  });

  it("only reserves space while the drawer is open", () => {
    const { rerender, unmount } = renderHook(({ open }) => useAiDrawerWidth(open), {
      initialProps: { open: false },
    });
    expect(document.documentElement).not.toHaveClass(AI_DRAWER_OPEN_CLASS);

    rerender({ open: true });
    expect(document.documentElement).toHaveClass(AI_DRAWER_OPEN_CLASS);

    unmount();
    expect(document.documentElement).not.toHaveClass(AI_DRAWER_OPEN_CLASS);
  });

  it("pulls the drawer in when the window becomes too narrow for it", () => {
    localStorage.setItem(AI_DRAWER_WIDTH_STORAGE_KEY, "640");
    const { result } = renderHook(() => useAiDrawerWidth(true));
    expect(result.current.width).toBe(640);

    act(() => {
      window.innerWidth = 1100;
      window.dispatchEvent(new Event("resize"));
    });
    expect(result.current.width).toBe(440); // 40% of 1100
    expect(result.current.maxWidth).toBe(440);
  });
});
