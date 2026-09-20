// What a tool call is ABOUT, in the user's words.
//
// The server addresses things by id, because ids are what the tools take.
// The browser already holds the lists those ids came from — the drawer
// primes pages, schedules, collections and plugins when it opens — so a
// card has no excuse to say "Delete schedule 289204ec-4306-41f0-…" when it
// could say "Delete schedule Goodnight · 21:00–23:00 · every day".
//
// Resolution is best-effort by construction: every branch falls back to
// `detailForTool`'s plain reading of the arguments (usually the id), so a
// cold cache, a deleted row, or a tool this file has never heard of still
// renders something true.

import { detailForTool, type TranslateFn } from "@/components/ai-tool-labels";
import type { CreateScheduleArgs, DayPattern, ToolCall } from "@/lib/ai-chat-types";

/** A row with a human name, which is all this file needs of most entities. */
interface NamedRow {
  id: string;
  name: string;
}

/** The subset of a schedule entry a card shows. */
interface ScheduleRow {
  id: string;
  page_id: string;
  start_time: string;
  end_time?: string | null;
  day_pattern: DayPattern;
  enabled: boolean;
}

/**
 * The query caches this file reads, in the shape the API returns them.
 * Every field is optional: a drawer opened before its queries resolve has
 * none of them.
 */
export interface TargetCaches {
  pages?: { pages?: NamedRow[] };
  schedules?: { schedules?: ScheduleRow[] };
  collections?: { collections?: NamedRow[] };
  plugins?: { plugins?: NamedRow[] };
  panels?: { panels?: NamedRow[] };
  boards?: { boards?: NamedRow[] };
}

/** The separator between the parallel facts of a resolved schedule. */
const SEP = " · ";

function nameOf(rows: NamedRow[] | undefined, id: unknown): string | undefined {
  if (typeof id !== "string" || !id) return undefined;
  return rows?.find((row) => row.id === id)?.name || undefined;
}

/** "21:00–23:00", or "21:00" for an open-ended entry. */
function window(start: string, end?: string | null): string | undefined {
  if (!start) return undefined;
  return end ? `${start}–${end}` : start;
}

function dayPattern(pattern: DayPattern | undefined, t: TranslateFn): string | undefined {
  if (!pattern) return undefined;
  const key = `dayPattern.${pattern}`;
  const text = t(key);
  // An unknown pattern from a newer server: say nothing rather than a key.
  return text === key ? undefined : text;
}

/** "Goodnight · 21:00–23:00 · every day", dropping any part it cannot fill. */
function describeSchedule(
  parts: { pageId: unknown; start?: string; end?: string | null; pattern?: DayPattern },
  caches: TargetCaches,
  t: TranslateFn,
): string | undefined {
  const pieces = [
    nameOf(caches.pages?.pages, parts.pageId),
    parts.start ? window(parts.start, parts.end) : undefined,
    dayPattern(parts.pattern, t),
  ].filter((piece): piece is string => !!piece);
  return pieces.length > 0 ? pieces.join(SEP) : undefined;
}

/**
 * The detail beside a tool card's title, resolved against the caches.
 *
 * Falls back to {@link detailForTool} — the plain reading of the arguments —
 * whenever a name cannot be found, so this never renders less than before.
 */
export function resolveToolDetail(
  call: Pick<ToolCall, "name" | "args">,
  caches: TargetCaches,
  t: TranslateFn,
): string | undefined {
  const args = call.args as Record<string, unknown>;
  const fallback = () => detailForTool(call);

  switch (call.name) {
    case "delete_schedule":
    case "update_schedule": {
      const entry = caches.schedules?.schedules?.find((s) => s.id === args.schedule_id);
      if (!entry) return fallback();
      return (
        describeSchedule(
          { pageId: entry.page_id, start: entry.start_time, end: entry.end_time, pattern: entry.day_pattern },
          caches,
          t,
        ) ?? fallback()
      );
    }
    case "create_schedule": {
      const a = args as unknown as CreateScheduleArgs;
      return (
        describeSchedule(
          { pageId: a.page_id, start: a.start_time, end: a.end_time, pattern: a.day_pattern },
          caches,
          t,
        ) ?? fallback()
      );
    }
    case "delete_page":
    case "update_page":
    case "get_page":
    case "preview_saved_page":
    case "set_active_page":
      return nameOf(caches.pages?.pages, args.page_id) ?? fallback();
    case "delete_collection":
    case "update_collection":
      return nameOf(caches.collections?.collections, args.collection_id) ?? fallback();
    case "install_plugin":
    case "enable_plugin":
    case "disable_plugin":
    case "uninstall_plugin":
    case "configure_plugin":
    case "update_plugin":
    case "get_plugin_data":
      return nameOf(caches.plugins?.plugins, args.plugin_id) ?? fallback();
    // Not tools the MCP server registers today (#2024 named them as the
    // destructive set to cover); mapped so they read as names the day they
    // arrive rather than as ids.
    case "delete_panel":
      return nameOf(caches.panels?.panels, args.panel_id) ?? fallback();
    case "remove_board":
      return nameOf(caches.boards?.boards, args.board_id) ?? fallback();
    default:
      return fallback();
  }
}
