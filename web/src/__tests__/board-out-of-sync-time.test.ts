import { describe, expect, it } from "vitest";

import { formatDetectedAt } from "@/lib/board-out-of-sync-time";

describe("formatDetectedAt", () => {
  it("never lets the time wrap between the digits and AM/PM", () => {
    const now = new Date("2026-10-18T00:30:00");
    const text = formatDetectedAt(new Date("2026-10-18T00:16:00").toISOString(), "en-US", now);
    expect(text).toMatch(/12:16/);
    expect(text).not.toMatch(/ /);
  });
});
