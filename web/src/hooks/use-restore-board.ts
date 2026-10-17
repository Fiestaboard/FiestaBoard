"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type BoardCurrentMessageResponse, type SilenceStatus } from "@/lib/api";
import { formatSilenceEnd } from "@/lib/board-out-of-sync-time";

/**
 * Restore the board over what another app wrote (issue #1945), and say what
 * actually happened.
 *
 * `POST /force-refresh` runs the install-wide send pass and answers `sent`:
 * True only when content reached the PRIMARY board. Silence and pause hold
 * the pass, and it then answers `sent: false` — so the banner must stay and
 * the toast must say nothing was sent, naming the reason the client knows
 * (pause, then silence). Writing the optimistic "in sync" frame on a held
 * send made the banner blink away and come back ~4 s later under a green
 * "Board restored".
 *
 * On a real send the user chose their page over the other app's, so the
 * remembered external frame is forgotten too (no "kept" notice follows).
 */
export function useRestoreBoard({
  boardId,
  paused,
  silenceStatus,
  isPrimary,
}: {
  boardId?: string;
  paused: boolean;
  silenceStatus?: SilenceStatus | null;
  isPrimary: boolean;
}): { restore: () => Promise<void>; isPending: boolean } {
  const t = useTranslations("boardOutOfSync");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);

  const restore = useCallback(async () => {
    setIsPending(true);
    try {
      const { sent } = await api.forceRefresh();
      if (!sent) {
        // No cache write and no refetch: the board still shows the other
        // app's content, and the banner says so.
        if (paused) {
          toast.warning(t("toastNotSentPaused"));
        } else if (silenceStatus?.active) {
          toast.warning(t("toastNotSentSilence", { time: formatSilenceEnd(silenceStatus.end_time_utc, locale) }));
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
          const { external_characters: _held, external_detected_at: _heldAt, ...rest } = old;
          return { ...rest, characters: old.expected_characters ?? old.characters };
        },
      );
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.boardCurrentMessage() });
      }, 4000);
      api.dismissExternalFrame(boardId).catch(() => {});
      toast.success(isPrimary ? t("toastRestored") : t("toastRestoredAll"));
    } catch {
      toast.error(t("toastRestoreFailed"));
    } finally {
      setIsPending(false);
    }
  }, [boardId, isPrimary, locale, paused, queryClient, silenceStatus, t]);

  return { restore, isPending };
}
