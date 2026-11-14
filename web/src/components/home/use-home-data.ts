import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { queryKeys } from "@/hooks/use-board";
import { api } from "@/lib/api";

/** Query key prefix for `GET /v1/boards/{board}`; the board id (or "primary") follows. */
export const BOARD_DETAIL_KEY = "boardDetail";
export const ACTIVE_TRIGGER_KEY = ["triggers", "active"] as const;

/**
 * One display's `GET /v1/boards/{board}`: H2's next change and H1's override
 * run. Polled every minute like the active-schedule read; the Countdown's
 * `onEnd` refetches it at the moment it matters.
 */
export function useBoardDetail(boardId: string | undefined) {
  return useQuery({
    queryKey: [BOARD_DETAIL_KEY, boardId || "primary"],
    queryFn: () => api.getBoardDetail(boardId),
    refetchInterval: 60_000,
  });
}

/**
 * The plugin trigger on the primary display, if any. Triggers drive the
 * primary only, so a non-primary Home never asks.
 */
export function useActiveTrigger(enabled: boolean) {
  return useQuery({
    queryKey: ACTIVE_TRIGGER_KEY,
    queryFn: () => api.getActiveTrigger(),
    enabled,
    refetchInterval: 30_000,
    select: (data) => data.trigger,
  });
}

/**
 * Refetch everything that says what a display shows. Called once per
 * `endsAt` by the Countdown (FiestaUI guarantees that, Strict Mode included),
 * and after either verb or a cancel.
 */
export function useRefreshHomeStatus() {
  const queryClient = useQueryClient();
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
    void queryClient.invalidateQueries({ queryKey: [BOARD_DETAIL_KEY] });
    void queryClient.invalidateQueries({ queryKey: ACTIVE_TRIGGER_KEY });
    void queryClient.invalidateQueries({ queryKey: queryKeys.boardCurrentMessage() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.activePage() });
  }, [queryClient]);
}

/**
 * Nudge ONE display to repaint now (`POST /v1/boards/{board}/restore`: forget
 * its dedupe and run its pass, which applies a timed message first). Not
 * `/force-refresh`, which repaints every display and spends every note
 * array's 15 s send window. A paused or silenced display answers 409; the
 * override's own cache drop still lands it on the next tick, so that is fine.
 */
export function nudgeDisplay(boardId: string | null | undefined): void {
  api.restoreBoard(boardId).catch(() => {});
}
