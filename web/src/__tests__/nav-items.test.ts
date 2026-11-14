import { describe, expect, it } from "vitest";

import type { PluginInfo } from "@/lib/api";
import {
  HELP_DOCS_URL,
  HUB_SETTINGS_LINKS,
  integrationsNeedingAttention,
  isNavItemActive,
  NAV_ITEMS,
  navItemsFor,
} from "@/lib/nav-items";

const byKey = (key: string) => NAV_ITEMS.find((item) => item.key === key)!;

describe("NAV_ITEMS (WEB-01 information architecture)", () => {
  it("is Home · Pages ▸ Collections · Schedule · Displays │ Integrations · Staff Picks · Settings · Help & Docs", () => {
    expect(NAV_ITEMS.map((item) => item.key)).toEqual([
      "home",
      "pages",
      "collections",
      "schedule",
      "displays",
      "integrations",
      "picks",
      "settings",
      "helpDocs",
    ]);
  });

  it("nests Collections under Pages", () => {
    expect(byKey("collections").nestedUnder).toBe("pages");
  });

  it("opens Help & Docs on the docs site", () => {
    expect(byKey("helpDocs")).toMatchObject({ href: HELP_DOCS_URL, external: true });
  });
});

describe("navItemsFor", () => {
  it("lists every destination on the rail", () => {
    expect(navItemsFor("rail")).toHaveLength(NAV_ITEMS.length);
  });

  it("puts Home, Pages, Schedule and Displays first on the tab bar, and leaves nested Collections out", () => {
    const keys = navItemsFor("bottom-nav").map((item) => item.key);
    expect(keys.slice(0, 4)).toEqual(["home", "pages", "schedule", "displays"]);
    expect(keys).not.toContain("collections");
    expect(keys.slice(4)).toEqual(["integrations", "picks", "settings", "helpDocs"]);
  });
});

describe("isNavItemActive", () => {
  it("lights Home only on /", () => {
    expect(isNavItemActive(byKey("home"), "/", "rail")).toBe(true);
    expect(isNavItemActive(byKey("home"), "/pages", "rail")).toBe(false);
  });

  it("lights a section on its sub-routes", () => {
    expect(isNavItemActive(byKey("settings"), "/settings/network", "rail")).toBe(true);
    expect(isNavItemActive(byKey("pages"), "/pages/edit/1", "rail")).toBe(true);
  });

  it("does not light Pages for a route that only shares its prefix", () => {
    expect(isNavItemActive(byKey("pages"), "/pagesx", "rail")).toBe(false);
  });

  it("lights Collections, not Pages, on /collections on the rail", () => {
    expect(isNavItemActive(byKey("collections"), "/collections/c1", "rail")).toBe(true);
    expect(isNavItemActive(byKey("pages"), "/collections/c1", "rail")).toBe(false);
  });

  it("lights Pages on /collections on the tab bar, where Collections has no tab", () => {
    expect(isNavItemActive(byKey("pages"), "/collections/c1", "bottom-nav")).toBe(true);
    expect(isNavItemActive(byKey("schedule"), "/collections/c1", "bottom-nav")).toBe(false);
  });

  it("never lights an external link", () => {
    expect(isNavItemActive(byKey("helpDocs"), HELP_DOCS_URL, "rail")).toBe(false);
  });
});

function plugin(overrides: Partial<PluginInfo>): PluginInfo {
  return { id: "p", enabled: true, configured: true, plugin_type: "data", ...overrides } as PluginInfo;
}

describe("integrationsNeedingAttention", () => {
  it("is 0 with no list yet", () => {
    expect(integrationsNeedingAttention(undefined)).toBe(0);
  });

  it("counts switched-on data integrations that are not set up", () => {
    expect(
      integrationsNeedingAttention([
        plugin({ id: "a", configured: false }),
        plugin({ id: "b", configured: false }),
        plugin({ id: "c" }),
      ]),
    ).toBe(2);
  });

  it("ignores switched-off integrations", () => {
    expect(integrationsNeedingAttention([plugin({ enabled: false, configured: false })])).toBe(0);
  });

  it("ignores outputs and transitions, which have nothing to set up", () => {
    expect(
      integrationsNeedingAttention([
        plugin({ plugin_type: "output", configured: false }),
        plugin({ plugin_type: "transition", configured: false }),
      ]),
    ).toBe(0);
  });

  it("treats a missing plugin_type as data (older hubs)", () => {
    expect(integrationsNeedingAttention([plugin({ plugin_type: undefined, configured: false })])).toBe(1);
  });
});

describe("HUB_SETTINGS_LINKS", () => {
  it("is Network · AI provider · System & backups · Language & time (07a, 07e)", () => {
    expect(HUB_SETTINGS_LINKS.map((link) => link.section)).toEqual([
      "network",
      "ai-provider",
      "system",
      "language-time",
    ]);
  });
});
