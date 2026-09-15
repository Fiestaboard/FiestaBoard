// Human labels for tool calls, keyed by MCP tool name.
//
// The server sends a `title` with every call (the tool's own annotation),
// which is the fallback; the translations here read better in a card and
// carry the one argument worth showing ("Create page · Morning").

import type {
  ConfigurePluginArgs,
  CreatePageArgs,
  CreateScheduleArgs,
  ToolCall,
  UpdatePageArgs,
  UpdateScheduleArgs,
  UpdateSettingArgs,
} from "@/lib/ai-chat-types";

export type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

const LABEL_KEYS: Record<string, string> = {
  create_page: "tool.createPage",
  update_page: "tool.updatePage",
  delete_page: "tool.deletePage",
  create_schedule: "tool.createSchedule",
  update_schedule: "tool.updateSchedule",
  delete_schedule: "tool.deleteSchedule",
  create_collection: "tool.createCollection",
  update_collection: "tool.updateCollection",
  delete_collection: "tool.deleteCollection",
  install_plugin: "tool.installPlugin",
  enable_plugin: "tool.enablePlugin",
  disable_plugin: "tool.disablePlugin",
  uninstall_plugin: "tool.uninstallPlugin",
  configure_plugin: "tool.configurePlugin",
  update_plugin: "tool.updatePlugin",
  set_active_page: "tool.setActivePage",
  set_schedule_mode: "tool.setScheduleMode",
  send_message: "tool.sendMessage",
  update_setting: "tool.updateSetting",
  trigger_system_update: "tool.triggerSystemUpdate",
  ask_user: "tool.askUser",
  list_pages: "tool.listPages",
  get_page: "tool.getPage",
  list_schedules: "tool.listSchedules",
  list_collections: "tool.listCollections",
  list_installed_plugins: "tool.listInstalledPlugins",
  list_registry_plugins: "tool.listRegistryPlugins",
  get_template_variables: "tool.getTemplateVariables",
  get_plugin_data: "tool.getPluginData",
  render_page_preview: "tool.renderPagePreview",
  preview_saved_page: "tool.previewSavedPage",
  validate_template: "tool.validateTemplate",
  get_system_status: "tool.getSystemStatus",
  get_settings_summary: "tool.getSettingsSummary",
  get_active_page: "tool.getActivePage",
  get_board_content: "tool.getBoardContent",
};

/** The card title. Unknown tools fall back to the server's own title. */
export function labelForTool(call: Pick<ToolCall, "name" | "title">, t: TranslateFn): string {
  const key = LABEL_KEYS[call.name];
  return key ? t(key) : call.title || call.name;
}

/** The one argument worth showing beside the title, if any. */
export function detailForTool(call: Pick<ToolCall, "name" | "args">): string | undefined {
  const args = call.args as Record<string, unknown>;
  switch (call.name) {
    case "create_page":
      return (args as unknown as CreatePageArgs).name;
    case "update_page":
    case "delete_page":
    case "get_page":
    case "preview_saved_page":
    case "set_active_page":
      return asText((args as unknown as UpdatePageArgs).page_id);
    case "create_schedule": {
      const a = args as unknown as CreateScheduleArgs;
      return a.start_time ? `${a.start_time}${a.end_time ? `–${a.end_time}` : ""}` : undefined;
    }
    case "update_schedule":
    case "delete_schedule":
      return asText((args as unknown as UpdateScheduleArgs).schedule_id);
    case "update_setting":
      return (args as unknown as UpdateSettingArgs).category;
    case "install_plugin":
    case "enable_plugin":
    case "disable_plugin":
    case "uninstall_plugin":
    case "configure_plugin":
    case "update_plugin":
    case "get_plugin_data":
      return asText((args as unknown as ConfigurePluginArgs).plugin_id);
    case "create_collection":
    case "update_collection":
    case "delete_collection":
      return asText(args.name ?? args.collection_id);
    case "send_message":
      return asText(args.text);
    default:
      return undefined;
  }
}

function asText(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}
