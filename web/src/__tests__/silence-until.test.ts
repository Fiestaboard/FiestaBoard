import { describe, expect, it } from "vitest";

import type { SilenceStatus } from "@/lib/api";
import { silenceEndsAt, silenceEndsAtLabel } from "@/lib/silence-until";

const now = Date.parse("2026-01-01T23:30:00Z");
const status = (fields: Partial<SilenceStatus> = {}) => ({ active: true, ...fields }) as SilenceStatus;

describe("silence end time", () => {
  it("prefers the absolute end, including a midnight boundary", () => {
    expect(
      silenceEndsAt(status({ ends_at_utc: "2026-01-02T07:00:00Z", seconds_until_next_change: 10 }), now)?.toISOString(),
    ).toBe("2026-01-02T07:00:00.000Z");
  });
  it("supports older status responses through a sampled countdown", () => {
    expect(silenceEndsAt(status({ seconds_until_next_change: 3600 }), now)?.toISOString()).toBe(
      "2026-01-02T00:30:00.000Z",
    );
  });
  it("does not quote an end for an inactive board", () => {
    expect(silenceEndsAt(status({ active: false, ends_at_utc: "2026-01-02T07:00:00Z" }), now)).toBeNull();
  });
  it.each([NaN, Infinity, -1])("rejects an invalid countdown %s", (seconds) => {
    expect(silenceEndsAt(status({ ends_at_utc: "invalid", seconds_until_next_change: seconds }), now)).toBeNull();
  });
  it("formats the time in the selected UI locale", () => {
    const sample = status({ ends_at_utc: "2026-01-02T07:00:00Z" });
    expect(silenceEndsAtLabel(sample, now, "de")).toBe(
      new Date(sample.ends_at_utc!).toLocaleTimeString("de", { hour: "numeric", minute: "2-digit" }),
    );
  });
});
