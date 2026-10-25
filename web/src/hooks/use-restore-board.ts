"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import { api, ApiError, type BoardCurrentMessageResponse } from "@/lib/api";

/**
 * Restore the board over what another app wrote (issue #1945), and say what
 * actually happened.
 *
 * `POST /v1/boards/{board}/restore` runs this one board's send pass (#2354);
 * it used to be the install-wide `/force-refresh`, which resent every display.
 * Pause (and silence, during which the banner is hidden) refuse it with 409,
 * and a pass that wrote nothing answers `sent: false` — either way the banner
 * must stay and the toast must say nothing was sent, naming pause when the
 * client knows it. Writing the optimistic "in sync" frame on a held send made
 * the banner blink away and come back ~4 s later under a green
 * "Board restored".
 *
 * On a real send the user chose their page over the other app's, so the
 * remembered external frame is forgotten too (no "kept" notice follows), and
 * so is a no-read-back display's "overwritten" mark (#2354), which the
 * backend clears on that same write.
 */
export function useRestoreBoard({ boardId, paused }: { boardId?: string; paused: boolean }): {
  restore: () => Promise<void>;
  isPending: boolean;
} {
  const t = useTranslations("boardOutOfSync");
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);

  const restore = useCallback(async () => {
    setIsPending(true);
    try {
      let sent: boolean;
      try {
        ({ sent } = await api.restoreBoard(boardId));
      } catch (error) {
        // 409 is policy (paused, or silenced since the banner rendered), not breakage.
        if (!(error instanceof ApiError && error.status === 409)) throw error;
        sent = false;
      }
      if (!sent) {
        // No cache write and no refetch: the board still shows the other
        // app's content, and the banner says so.
        if (paused) {
          toast.warning(t("toastNotSentPaused"));
        } else {
          toast.warning(t("toastNotSent"));
        }
        return;
      }
      // Optimistically mark the board in sync (and the frame forgotten) so
      // the banner goes at once. The backend reads the board back ~3 s after
      // a send; the refetch at 4 s confirms it.
      queryClient.setQueryData(
        queryKeys.boardCurrentMessage(boardId),
        (old: BoardCurrentMessageResponse | undefined) => {
          if (!old) return old;
          const {
            external_characters: _held,
            external_detected_at: _heldAt,
            overwritten_at: _overwrittenAt,
            ...rest
          } = old;
          return { ...rest, characters: old.expected_characters ?? old.characters };
        },
      );
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.boardCurrentMessage() });
      }, 4000);
      api.dismissExternalFrame(boardId).catch(() => {});
      toast.success(t("toastRestored"));
    } catch {
      toast.error(t("toastRestoreFailed"));
    } finally {
      setIsPending(false);
    }
  }, [boardId, paused, queryClient, t]);

  return { restore, isPending };
}
