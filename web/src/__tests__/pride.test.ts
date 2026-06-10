import { describe, expect, it } from "vitest";

import { HIDE_FESTIVE_COOKIE, shouldShowPride } from "@/lib/pride";

describe("shouldShowPride", () => {
  const june = new Date("2026-06-08T12:00:00Z");
  const july = new Date("2026-07-01T12:00:00Z");

  it("returns false outside of June regardless of cookie", () => {
    expect(shouldShowPride(july, "")).toBe(false);
    expect(shouldShowPride(july, `${HIDE_FESTIVE_COOKIE}=true`)).toBe(false);
  });

  it("returns true in June with no opt-out cookie", () => {
    expect(shouldShowPride(june, "")).toBe(true);
    expect(shouldShowPride(june, "other=1; another=2")).toBe(true);
  });

  it("returns false in June when the hide_festive_months=true cookie is set", () => {
    expect(shouldShowPride(june, `${HIDE_FESTIVE_COOKIE}=true`)).toBe(false);
    expect(shouldShowPride(june, `theme=dark; ${HIDE_FESTIVE_COOKIE}=true; locale=en`)).toBe(false);
  });

  it("still returns true if the cookie value is not exactly 'true'", () => {
    // A stale `hide_festive_months=` (cleared) cookie must not suppress.
    expect(shouldShowPride(june, `${HIDE_FESTIVE_COOKIE}=`)).toBe(true);
    expect(shouldShowPride(june, `${HIDE_FESTIVE_COOKIE}=false`)).toBe(true);
  });
});
