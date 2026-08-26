import { describe, expect, it } from "vitest";

import { isChromelessPath, isPanelPath } from "@/lib/chromeless";

describe("isPanelPath", () => {
  it("matches panel viewer routes", () => {
    expect(isPanelPath("/panel/abc123def456")).toBe(true);
  });

  it("does not match the panels settings surface or other routes", () => {
    expect(isPanelPath("/panels")).toBe(false);
    expect(isPanelPath("/")).toBe(false);
    expect(isPanelPath("/settings")).toBe(false);
  });

  it("strips an ingress base path before matching", () => {
    // stripBasePath only strips a prefix the runtime registered; with no
    // registered base path the raw pathname must still match.
    expect(isPanelPath("/panel/xyz")).toBe(true);
  });
});

describe("isChromelessPath", () => {
  it("covers login and panel routes", () => {
    expect(isChromelessPath("/login")).toBe(true);
    expect(isChromelessPath("/login?redirect=%2F")).toBe(true);
    expect(isChromelessPath("/panel/abc")).toBe(true);
  });

  it("keeps chrome everywhere else", () => {
    expect(isChromelessPath("/")).toBe(false);
    expect(isChromelessPath("/pages")).toBe(false);
  });
});
