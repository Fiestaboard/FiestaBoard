// Which cached queries a tool's result makes stale.
//
// The server reports what a tool did (`tool_result`), not which of the
// browser's caches that touches — the query keys are a web concern, and the
// MCP server must not learn them. This is the web-side mirror of the tool
// list: one entry per tool that writes, keyed by the MCP tool name, plus a
// broad fallback for a tool this map does not know so a new server tool
// still refreshes the screen.

import type { SettingCategory, ToolCall, UpdateSettingArgs } from "@/lib/ai-chat-types";

type Keys = readonly (readonly string[])[];

const PLUGINS: Keys = [["plugins"], ["registry-plugins"]];

/** Keys per tool. Prefix keys: `["schedules"]` matches `["schedules", boardId]` too. */
export const TOOL_QUERY_KEYS: Record<string, Keys> = {
  create_page: [["pages"], ["pagePreview"]],
  update_page: [["pages"], ["page"], ["pagePreview"], ["activePage"], ["status"]],
  delete_page: [["pages"], ["schedules"], ["collections"], ["activePage"]],
  create_schedule: [["schedules"]],
  update_schedule: [["schedules"]],
  delete_schedule: [["schedules"]],
  create_collection: [["collections"]],
  update_collection: [["collections"]],
  delete_collection: [["collections"], ["schedules"]],
  install_plugin: PLUGINS,
  enable_plugin: PLUGINS,
  disable_plugin: PLUGINS,
  uninstall_plugin: PLUGINS,
  configure_plugin: PLUGINS,
  update_plugin: PLUGINS,
  set_active_page: [["activePage"], ["active-page"], ["status"], ["boardCurrentMessage"]],
  set_schedule_mode: [["schedules"], ["status"]],
  send_message: [["boardCurrentMessage"], ["status"]],
  // A system update recreates the container; nothing local is worth refetching.
  trigger_system_update: [],
};

/** update_setting refreshes only the category it touched. */
export const SETTING_QUERY_KEYS: Record<SettingCategory, Keys> = {
  display: [["display-settings"], ["all-settings"]],
  transitions: [["transition-settings"], ["all-settings"]],
  output: [["output-settings"], ["all-settings"]],
  polling: [["polling-settings"], ["all-settings"]],
  location: [["location-settings"], ["all-settings"]],
  silence_schedule: [["silence-schedule"], ["all-settings"], ["silenceStatus"]],
  active_page: [["active-page"], ["activePage"], ["status"]],
};

/** Read-only tools touch nothing; unknown writers refresh the usual suspects. */
const BROAD: Keys = [["pages"], ["schedules"], ["collections"], ["plugins"]];

export function queryKeysForTool(call: Pick<ToolCall, "name" | "args" | "read_only">): Keys {
  if (call.read_only) return [];
  if (call.name === "update_setting") {
    const category = (call.args as unknown as UpdateSettingArgs).category;
    return SETTING_QUERY_KEYS[category] ?? [["all-settings"]];
  }
  return TOOL_QUERY_KEYS[call.name] ?? BROAD;
}
