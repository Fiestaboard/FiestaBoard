// Where a tool's change shows up on screen.

import type { ToolCall } from "@/lib/ai-chat-types";

import { settingsHref } from "./anchors";

/**
 * Where a tool's change shows up. Pattern-matched on the tool name so a new
 * tool lands in the right place by convention; the generic script points
 * at the most specific anchor it can name from the call's arguments.
 */
export function homeFor(call: Pick<ToolCall, "name" | "args">): { href: string; anchor: string } {
  const { name, args } = call;
  const id = (key: string): string | undefined => (typeof args[key] === "string" ? (args[key] as string) : undefined);

  if (/schedule|default_page/.test(name)) {
    const sid = id("schedule_id");
    return {
      href: "/schedule",
      anchor: sid
        ? `schedule.row.${sid}`
        : name === "set_schedule_mode"
          ? "schedule.mode"
          : name === "set_default_page"
            ? "schedule.default-page"
            : "schedule.root",
    };
  }
  if (/collection/.test(name)) {
    const cid = id("collection_id");
    return { href: "/collections", anchor: cid ? `collection.${cid}` : "collections.root" };
  }
  if (/plugin/.test(name)) {
    const pid = id("plugin_id");
    return { href: "/integrations", anchor: pid ? `plugin.${pid}` : "integrations.root" };
  }
  if (/panel|hdmi|board_size|identify_tile|_board$|^add_board|^remove_board|^update_board/.test(name)) {
    return { href: settingsHref("boards"), anchor: name.includes("panel") ? "settings.panels" : "settings.boards" };
  }
  if (/wifi|network/.test(name)) return { href: "/settings?section=network", anchor: "settings.network" };
  if (/system|restart|shutdown|backup|release|update_check|check_for_update/.test(name)) {
    return { href: "/settings?section=system", anchor: "settings.system" };
  }
  if (/debug|blank_board|fill_board|clear_board_cache|diagnostics/.test(name)) {
    return { href: "/settings?section=advanced", anchor: "settings.debug" };
  }
  if (/active_page|override|send_message|force_refresh|pause_board|resume_board|silence|board_content/.test(name)) {
    return { href: "/", anchor: "home.active-display" };
  }
  if (/transition/.test(name)) return { href: "/transitions", anchor: "transitions.root" };
  if (/staff_pick/.test(name)) return { href: "/picks", anchor: "picks.root" };
  const pid = id("page_id");
  return { href: "/pages", anchor: pid ? `page.${pid}` : "pages.root" };
}
