import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AI_DRAWER_WIDTH_STORAGE_KEY,
  clampDrawerWidth,
  DEFAULT_AI_DRAWER_WIDTH,
  MAX_AI_DRAWER_WIDTH,
  maxDrawerWidth,
  MIN_AI_DRAWER_WIDTH,
  readStoredDrawerWidth,
  storeDrawerWidth,
} from "@/lib/ai-drawer-width";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("maxDrawerWidth", () => {
  it("caps at 40% of the viewport on a screen where 720px would swallow the page", () => {
    expect(maxDrawerWidth(1440)).toBe(576);
  });

  it("never exceeds the 720px ceiling however wide the screen", () => {
    expect(maxDrawerWidth(3840)).toBe(MAX_AI_DRAWER_WIDTH);
  });

  it("never falls below the minimum on a narrow viewport", () => {
    expect(maxDrawerWidth(600)).toBe(MIN_AI_DRAWER_WIDTH);
  });
});

describe("clampDrawerWidth", () => {
  it("holds a drag at the 360px floor", () => {
    expect(clampDrawerWidth(120, 1440)).toBe(MIN_AI_DRAWER_WIDTH);
  });

  it("holds a drag at the viewport-derived ceiling", () => {
    expect(clampDrawerWidth(2000, 1440)).toBe(576);
  });

  it("passes a width inside the range through untouched", () => {
    expect(clampDrawerWidth(500, 1440)).toBe(500);
  });

  it("rounds to whole pixels so the stored value and the style agree", () => {
    expect(clampDrawerWidth(500.6, 1440)).toBe(501);
  });

  it("falls back to the default for a width that is not a number", () => {
    expect(clampDrawerWidth(Number.NaN, 1440)).toBe(DEFAULT_AI_DRAWER_WIDTH);
  });
});

describe("readStoredDrawerWidth", () => {
  it("reads back a width this viewer chose", () => {
    localStorage.setItem(AI_DRAWER_WIDTH_STORAGE_KEY, "512");
    expect(readStoredDrawerWidth()).toBe(512);
  });

  it("returns null when nothing is stored", () => {
    expect(readStoredDrawerWidth()).toBeNull();
  });

  it("returns null for junk rather than a NaN width", () => {
    localStorage.setItem(AI_DRAWER_WIDTH_STORAGE_KEY, "wide please");
    expect(readStoredDrawerWidth()).toBeNull();
  });

  it("returns null when storage itself throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(readStoredDrawerWidth()).toBeNull();
  });
});

describe("storeDrawerWidth", () => {
  it("writes the width for the next visit", () => {
    storeDrawerWidth(448);
    expect(localStorage.getItem(AI_DRAWER_WIDTH_STORAGE_KEY)).toBe("448");
  });

  it("swallows a storage failure instead of breaking the drag", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => storeDrawerWidth(448)).not.toThrow();
  });
});
