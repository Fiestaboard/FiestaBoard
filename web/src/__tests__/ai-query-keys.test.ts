import { describe, expect, it } from "vitest";

import { KNOWN_TOOL_NAMES, type ToolCall } from "@/lib/ai-chat-types";
import { queryKeysForTool, SETTING_QUERY_KEYS, TOOL_QUERY_KEYS } from "@/lib/ai-choreography/query-keys";

function call(name: string, args: Record<string, unknown> = {}, read_only = false): ToolCall {
  return { id: "x", name, args, title: name, read_only, destructive: false, requires_approval: false, source: "mcp" };
}

describe("queryKeysForTool", () => {
  it("covers every known tool that writes", () => {
    const writers = KNOWN_TOOL_NAMES.filter((n) => !/^(list_|get_|render_|preview_|validate_|ask_user)/.test(n));
    for (const name of writers) {
      expect(name === "update_setting" || name in TOOL_QUERY_KEYS, `${name} has no query keys`).toBe(true);
    }
  });

  it("refreshes only the category a setting change touched", () => {
    expect(queryKeysForTool(call("update_setting", { category: "location", values: {} }))).toEqual(
      SETTING_QUERY_KEYS.location,
    );
  });

  it("refreshes nothing for a read-only tool", () => {
    expect(queryKeysForTool(call("list_pages", {}, true))).toEqual([]);
  });

  it("refreshes the usual suspects for a writer it does not know", () => {
    expect(queryKeysForTool(call("brand_new_tool"))).toEqual([["pages"], ["schedules"], ["collections"], ["plugins"]]);
  });

  it("uses prefix keys for board-scoped schedule caches", () => {
    expect(queryKeysForTool(call("create_schedule"))).toEqual([["schedules"]]);
  });
});
