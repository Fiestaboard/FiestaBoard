import { describe, expect, it } from "vitest";

import { changedPageSettings } from "@/lib/ide/page-settings";

describe("changedPageSettings (UX-7-1 discard list)", () => {
  const saved = { duration_seconds: 300, transition_strategy: null };

  it("names a changed duration and transition", () => {
    expect(changedPageSettings({ duration_seconds: 60, transition_strategy: "row" }, saved)).toEqual([
      "duration",
      "transition",
    ]);
  });

  it("names nothing when the settings match the saved page", () => {
    expect(changedPageSettings({ duration_seconds: 300, transition_strategy: null }, saved)).toEqual([]);
    expect(changedPageSettings({ duration_seconds: 300 }, saved)).toEqual([]);
  });

  it("names nothing without both sides", () => {
    expect(changedPageSettings(null, saved)).toEqual([]);
    expect(changedPageSettings({ duration_seconds: 60 }, undefined)).toEqual([]);
  });
});
