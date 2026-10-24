"use client";

import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/hooks/use-board";
import { useLocale } from "@/i18n/translations";
import type { HeldSendSummary, SilenceStatus } from "@/lib/api";
import { api } from "@/lib/api";
import { silenceEndsAtLabel } from "@/lib/silence-until";

export interface SilenceState {
  status: SilenceStatus | undefined;
  availability: "loading" | "error" | "known";
  refresh: () => Promise<unknown>;
  /** The board is inside its silence window right now. */
  active: boolean;
  /** When silence ends, formatted for the viewer ("7:00 AM"); null if unknown or not silenced. */
  until: string | null;
  /** Sends refused during silence are held and shown when it ends (`show_queued_on_exit`). */
  holds: boolean;
  /** The send this board is holding, if any. */
  held: HeldSendSummary | null;
  queueAvailable: boolean;
}

/**
 * One board's silence state, from the same `/silence-status` query (and the
 * same 30 s poll) the silence-imminent banner uses (#1943). Every silence
 * control reads this hook, so the time and wording are identical everywhere.
 *
 * `boardId` undefined reads the primary board.
 */
export function useSilence(boardId?: string): SilenceState {
  const locale = useLocale();
  const {
    data: status,
    dataUpdatedAt,
    isError,
    isFetching,
    refetch,
  } = useQuery<SilenceStatus>({
    queryKey: queryKeys.silenceStatus(boardId),
    queryFn: () => api.getSilenceStatus(boardId),
    refetchInterval: 30_000,
  });
  const active = status?.active === true;
  const availability: SilenceState["availability"] = isFetching
    ? "loading"
    : isError
      ? "error"
      : typeof status?.active === "boolean"
        ? "known"
        : "loading";
  return {
    status,
    availability,
    refresh: refetch,
    active,
    until: active ? silenceEndsAtLabel(status, dataUpdatedAt, locale) : null,
    holds: status?.holds_blocked_sends === true,
    held: status?.queue_available === false ? null : (status?.held ?? null),
    queueAvailable: status?.queue_available !== false,
  };
}
