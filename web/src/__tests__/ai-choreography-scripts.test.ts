import { describe, expect, it, vi } from "vitest";

import { KNOWN_TOOL_NAMES, type ToolCall, type ToolResult } from "@/lib/ai-chat-types";
import { anchorSelectors, SETTING_SECTIONS, settingAnchors, settingsHref } from "@/lib/ai-choreography/anchors";
import { homeFor } from "@/lib/ai-choreography/home";
import { getScript, scriptedTools } from "@/lib/ai-choreography/registry";
import { formatSettingValue } from "@/lib/ai-choreography/scripts/settings";
import type { ChoreographyContext, Step } from "@/lib/ai-choreography/types";

const BASE: ToolCall = {
  id: "tc1",
  name: "create_page",
  args: {},
  title: "Create page",
  read_only: false,
  destructive: false,
  requires_approval: false,
  source: "mcp",
};

const OK: ToolResult = {
  id: "tc1",
  name: "create_page",
  status: "ok",
  summary: "ok",
  result: { page_id: "p9" },
  error: null,
};

function ctxWith(overrides: Partial<ChoreographyContext> = {}): ChoreographyContext {
  return {
    navigate: vi.fn(),
    pathname: () => "/",
    spotlight: { show: vi.fn(), caption: vi.fn(), pulse: vi.fn(), hide: vi.fn(), ghost: vi.fn(), clearGhosts: vi.fn() },
    pageEditor: {
      isMounted: () => false,
      pageId: () => undefined,
      hasUnsavedChanges: () => false,
      begin: vi.fn(),
      setName: vi.fn(),
      setLine: vi.fn(),
      setDeviceType: vi.fn(),
      discard: vi.fn(),
      reload: async () => {},
      waitFor: async () => true,
    },
    schedule: {
      isMounted: () => false,
      openEmpty: vi.fn(),
      openEntry: vi.fn(),
      setField: vi.fn(),
      close: vi.fn(),
      waitFor: async () => true,
      waitForForm: async () => true,
    },
    t: (key, params) => (params ? `${key}(${Object.values(params).join(",")})` : key),
    label: (call) => call.title,
    reducedMotion: false,
    ...overrides,
  };
}

const kinds = (steps: Step[]) => steps.map((s) => s.kind);
const navigations = (steps: Step[]) => steps.flatMap((s) => (s.kind === "navigate" ? [s.href] : []));
const typed = (steps: Step[]) => steps.flatMap((s) => (s.kind === "type" ? [s.value] : []));

describe("homeFor", () => {
  it("points every known writing tool at a route and an anchor", () => {
    for (const name of KNOWN_TOOL_NAMES) {
      const { href, anchor } = homeFor({ name, args: {} });
      expect(href, name).toMatch(/^\//);
      expect(anchor, name).toMatch(/^[a-z]+[a-z0-9.\-_]*$/);
    }
  });

  it("names the specific row or card when the call carries an id", () => {
    expect(homeFor({ name: "delete_page", args: { page_id: "p1" } })).toEqual({ href: "/pages", anchor: "page.p1" });
    expect(homeFor({ name: "delete_schedule", args: { schedule_id: "s1" } })).toEqual({
      href: "/schedule",
      anchor: "schedule.row.s1",
    });
    expect(homeFor({ name: "configure_plugin", args: { plugin_id: "weather" } })).toEqual({
      href: "/integrations",
      anchor: "plugin.weather",
    });
    expect(homeFor({ name: "update_collection", args: { collection_id: "c1" } })).toEqual({
      href: "/collections",
      anchor: "collection.c1",
    });
  });

  it("sends board state to the dashboard and hardware to the settings tab", () => {
    expect(homeFor({ name: "set_active_page", args: {} }).href).toBe("/");
    expect(homeFor({ name: "send_message", args: {} }).anchor).toBe("home.active-display");
    expect(homeFor({ name: "update_board", args: {} }).href).toBe("/settings?section=hardware");
    expect(homeFor({ name: "restart_system", args: {} }).href).toBe("/settings?section=system");
  });
});

describe("anchors", () => {
  it("prefers the data attribute and falls back to a legacy id", () => {
    expect(anchorSelectors("page-editor.name")).toEqual(['[data-ai-anchor="page-editor.name"]', "#page-name"]);
    expect(anchorSelectors("plugin.weather")).toEqual(['[data-ai-anchor="plugin.weather"]']);
  });

  it("maps every setting category to a tab", () => {
    for (const category of Object.keys(SETTING_SECTIONS)) {
      expect(settingsHref(category)).toMatch(/^\/settings\?section=/);
    }
    expect(settingAnchors("general", "instance_name")).toEqual({
      control: "settings.general.instance_name",
      card: "settings.general",
    });
    expect(settingAnchors("silence_schedule", "mode").card).toBe("settings.silence_schedule");
  });
});

describe("scripts", () => {
  it("has a script or the fallback for every known tool, and none for read-only calls", () => {
    for (const name of KNOWN_TOOL_NAMES) expect(getScript(name)).toBeTruthy();
    const ctx = ctxWith();
    const readOnly = { ...BASE, name: "list_pages", read_only: true };
    expect(getScript("list_pages").narrate(readOnly, ctx)).toEqual([]);
    expect(scriptedTools()).toContain("create_page");
  });

  it("create_page walks to a fresh editor and types the name and every line", () => {
    const ctx = ctxWith();
    const call = { ...BASE, args: { name: "Morning", template_lines: ["HELLO", "", "WORLD"], device_type: "note" } };
    const steps = getScript("create_page").narrate(call, ctx);
    expect(navigations(steps)).toEqual(["/pages", "/pages/new?device=note&fresh=1"]);
    expect(kinds(steps)).toContain("waitBridge");
    expect(typed(steps)).toEqual(["Morning", "HELLO", "", "WORLD"]);
  });

  it("create_page continues from what the draft already typed", () => {
    const ctx = ctxWith();
    const script = getScript("create_page");
    const progress: Record<string, unknown> = {};
    const first = script.draft!(
      { name: "create_page", strings: { name: "Morning" }, lists: { template_lines: ["HELLO"] } },
      ctx,
      progress,
    );
    expect(typed(first)).toEqual(["Morning", "HELLO"]);
    const second = script.draft!(
      {
        name: "create_page",
        strings: { name: "Morning" },
        lists: { template_lines: ["HELLO"] },
        partial: { key: "template_lines", index: 1, value: "WO" },
      },
      ctx,
      progress,
    );
    expect(typed(second)).toEqual([]);
    expect(second.some((s) => s.kind === "set" && s.value === "WO")).toBe(true);
    const call = { ...BASE, args: { name: "Morning", template_lines: ["HELLO", "WORLD"] } };
    const rest = script.narrate(call, ctx, progress);
    expect(navigations(rest)).toEqual([]);
    expect(typed(rest)).toEqual(["WORLD"]);
  });

  it("create_page settles by discarding the staged draft and opening the saved page", () => {
    const ctx = ctxWith();
    const steps = getScript("create_page").settle(BASE, OK, ctx);
    expect(navigations(steps)).toEqual(["/pages/edit/p9"]);
    expect(kinds(steps)[0]).toBe("run");
    expect(kinds(steps)).toContain("pulse");
    expect(kinds(steps).at(-1)).toBe("hide");
  });

  it("create_page stop and fail both discard the staging", () => {
    const ctx = ctxWith();
    const script = getScript("create_page");
    for (const steps of [
      script.stop!(BASE, ctx),
      script.fail!(BASE, { ...OK, status: "error", error: "taken" }, ctx),
    ]) {
      const run = steps.find((s) => s.kind === "run");
      expect(run).toBeTruthy();
      (run as Extract<Step, { kind: "run" }>).run(ctx);
      expect(ctx.pageEditor.discard).toHaveBeenCalled();
    }
  });

  it("update_page never types over unsaved edits", () => {
    const ctx = ctxWith({
      pageEditor: { ...ctxWith().pageEditor, isMounted: () => true, pageId: () => "p1", hasUnsavedChanges: () => true },
    });
    const call = { ...BASE, name: "update_page", args: { page_id: "p1", template_lines: ["X"] } };
    const steps = getScript("update_page").narrate(call, ctx);
    expect(typed(steps)).toEqual([]);
    expect(kinds(steps)).toEqual(["spotlight"]);
  });

  it("update_page opens the page first when the editor holds another one", () => {
    const ctx = ctxWith({ pageEditor: { ...ctxWith().pageEditor, isMounted: () => true, pageId: () => "other" } });
    const call = { ...BASE, name: "update_page", args: { page_id: "p1", name: "Dawn", device_type: "note" } };
    const steps = getScript("update_page").narrate(call, ctx);
    expect(navigations(steps)).toEqual(["/pages/edit/p1"]);
    expect(steps.some((s) => s.kind === "set" && s.value === "note")).toBe(true);
    expect(typed(steps)).toEqual(["Dawn"]);
  });

  it("create_schedule opens an empty form and fills the fields top to bottom", () => {
    const ctx = ctxWith();
    const call = {
      ...BASE,
      name: "create_schedule",
      args: { enabled: true, page_id: "p1", start_time: "06:45", day_pattern: "weekdays" },
    };
    const steps = getScript("create_schedule").narrate(call, ctx);
    expect(navigations(steps)).toEqual(["/schedule"]);
    const fields = steps.flatMap((s) =>
      s.kind === "set" && s.target.bridge === "schedule-form" ? [s.target.field] : [],
    );
    expect(fields).toEqual(["page_id", "start_time", "day_pattern", "enabled"]);
  });

  it("update_setting ghosts every value on its control and pulses the card", () => {
    const ctx = ctxWith();
    const call = {
      ...BASE,
      name: "update_setting",
      args: { category: "general", values: { instance_name: "Kitchen", time_format: "24h" } },
    };
    const steps = getScript("update_setting").narrate(call, ctx);
    expect(navigations(steps)).toEqual(["/settings?section=general"]);
    const ghosts = steps.filter((s) => s.kind === "ghost") as Extract<Step, { kind: "ghost" }>[];
    expect(ghosts.map((g) => g.value)).toEqual(["Kitchen", "24h"]);
    const settle = getScript("update_setting").settle(call, OK, ctx);
    expect(kinds(settle)).toContain("pulse");
  });

  it("the fallback shows every writer where it lands and says when it is done", () => {
    const ctx = ctxWith();
    const call = { ...BASE, name: "brand_new_tool", args: { plugin_id: "weather" }, title: "Brand new" };
    expect(navigations(getScript("brand_new_tool").narrate(call, ctx))).toEqual(["/integrations"]);
    const settle = getScript("brand_new_tool").settle(call, OK, ctx);
    expect(settle.some((s) => s.kind === "caption" && s.caption === "done(Brand new)")).toBe(true);
    expect(getScript("brand_new_tool").approvalAnchor!(call, ctx)).toBe("plugin.weather");
  });

  it("formats setting values for the ghost", () => {
    const t = (key: string) => key;
    expect(formatSettingValue(true, t)).toBe("on");
    expect(formatSettingValue(false, t)).toBe("off");
    expect(formatSettingValue(30, t)).toBe("30");
    expect(formatSettingValue(null, t)).toBe("—");
    expect(formatSettingValue({ a: 1 }, t)).toBe('{"a":1}');
  });
});
