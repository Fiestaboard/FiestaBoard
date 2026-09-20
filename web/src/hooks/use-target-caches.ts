"use client";

import { useQueryClient } from "@tanstack/react-query";

import type { TranslateFn } from "@/components/ai-tool-labels";
import { detailForTool } from "@/components/ai-tool-labels";
import { useTranslations } from "@/i18n/translations";
import type { ToolCall } from "@/lib/ai-chat-types";
import { resolveToolDetail, type TargetCaches } from "@/lib/ai-target-names";

/**
 * Names already worked out, keyed by tool-call id.
 *
 * A delete removes its target from the cache, so the card that reports
 * "Done" would name by uuid the very thing whose name it knew a second
 * earlier, while it was asking permission to delete it. The card describes
 * something that already happened, so the name it had at the time is the
 * right name to keep.
 *
 * Module-level rather than per-component: the transcript remounts when a
 * conversation is reloaded, and a call's identity is its id, not its place
 * in a tree. Cleared wholesale past a generous cap — this is a display
 * nicety, not a store.
 */
const REMEMBERED_DETAILS = new Map<string, string>();
const REMEMBERED_LIMIT = 500;

/** Test seam: forget what has been resolved so far. */
export function clearRememberedToolDetails(): void {
  REMEMBERED_DETAILS.clear();
}

/**
 * The resolved name for a call, remembered once found.
 *
 * Falls back to the plain argument reading until the caches can name the
 * target, and keeps the name once they have — including after the target
 * is gone.
 */
export function rememberedToolDetail(
  call: Pick<ToolCall, "id" | "name" | "args">,
  caches: TargetCaches,
  t: TranslateFn,
): string | undefined {
  const resolved = resolveToolDetail(call, caches, t);
  if (!call.id) return resolved;
  if (resolved !== undefined && resolved !== detailForTool(call)) {
    if (REMEMBERED_DETAILS.size >= REMEMBERED_LIMIT) REMEMBERED_DETAILS.clear();
    REMEMBERED_DETAILS.set(call.id, resolved);
    return resolved;
  }
  return REMEMBERED_DETAILS.get(call.id) ?? resolved;
}

/**
 * The lists a tool card needs to turn ids into names, read straight from
 * the query cache.
 *
 * Prefix matching matters: schedules are cached per board
 * (`["schedules", boardId]`), so an exact `getQueryData(["schedules"])`
 * would miss them on a multi-board install. The first cached page of each
 * kind is enough — every board's schedules carry their own ids.
 *
 * Deliberately NOT a subscription. These caches are primed by the drawer
 * when it opens and change only when a tool writes to them, which already
 * re-renders the transcript; subscribing here would re-render every card on
 * every unrelated refetch.
 */
export function useTargetCaches(): TargetCaches {
  const queryClient = useQueryClient();
  const read = <T>(key: string): T | undefined =>
    queryClient.getQueriesData<T>({ queryKey: [key] }).find(([, data]) => data !== undefined)?.[1];

  return {
    pages: read("pages"),
    schedules: read("schedules"),
    collections: read("collections"),
    plugins: read("plugins"),
    panels: read("panels"),
    boards: read("boards"),
  };
}

/**
 * What this call is about, in the user's words — the resolved name where
 * the caches know it, the plain argument reading where they do not.
 */
export function useToolDetail(call: Pick<ToolCall, "id" | "name" | "args">): string | undefined {
  const caches = useTargetCaches();
  const t = useTranslations("aiChatPanel");
  return rememberedToolDetail(call, caches, t);
}
