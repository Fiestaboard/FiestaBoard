import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Text,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { useCurrentBoard } from "@/components/current-board-context";
import { ChangePageDialog } from "@/components/home/change-page-dialog";
import { scheduleNextChange } from "@/components/home/home-status";
import { BOARD_DETAIL_KEY } from "@/components/home/use-home-data";
import { queryKeys, useBoardSettings, useCollections, usePages } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { BoardInstance, Collection } from "@/lib/api";
import { api } from "@/lib/api";
import { silenceEndsAtLabel } from "@/lib/silence-until";

function StateDialog({ failed, retry, onClose }: { failed: boolean; retry: () => void; onClose: () => void }) {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("showNowAction")}</DialogTitle>
          <DialogDescription>{t(failed ? "safetyUnavailable" : "safetyLoading")}</DialogDescription>
        </DialogHeader>
        <Text role={failed ? "alert" : "status"}>{t(failed ? "safetyUnavailable" : "safetyLoading")}</Text>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {tc("cancel")}
          </Button>
          {failed && (
            <Button variant="outline" onClick={retry}>
              {t("retryButton")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Resolve the intended display before mounting any actionable send controls. */
export function CollectionShowNow({ collection, onClose }: { collection: Collection; onClose: () => void }) {
  const { currentBoardId, currentBoard, boards, isLoading } = useCurrentBoard();
  const settings = useBoardSettings();
  const allBoards = settings.data?.boards ?? boards;
  const board = allBoards.find((b) => b.id === (currentBoardId || currentBoard?.id)) ?? allBoards[0];
  if (isLoading || settings.isPending || settings.isFetching || settings.isError || !settings.data || !board) {
    return (
      <StateDialog
        failed={settings.isError || (!settings.isPending && !settings.isFetching && !isLoading && !board)}
        retry={() => {
          void settings.refetch();
        }}
        onClose={onClose}
      />
    );
  }
  return <ReadyShowNow key={board.id} board={board} collection={collection} onClose={onClose} />;
}

function ReadyShowNow({
  board,
  collection,
  onClose,
}: {
  board: BoardInstance;
  collection: Collection;
  onClose: () => void;
}) {
  const tn = useTranslations("home.nowShowing");
  // Entry reads are fresh and explicitly scoped even for the primary board.
  // Unknown override/silence state must never become a guessed false value.
  const fresh = { retry: false, refetchOnMount: "always", refetchOnWindowFocus: false } as const;
  const detail = useQuery({
    queryKey: [BOARD_DETAIL_KEY, board.id],
    queryFn: () => api.getBoardDetail(board.id),
    ...fresh,
  });
  const active = useQuery({
    queryKey: ["schedules", "active", board.id],
    queryFn: () => api.getActiveSchedule(board.id),
    ...fresh,
  });
  const silence = useQuery({
    queryKey: queryKeys.silenceStatus(board.id),
    queryFn: () => api.getSilenceStatus(board.id),
    ...fresh,
  });
  const { data: pages } = usePages();
  const { data: collections } = useCollections();
  const pending = [detail, active, silence].some((q) => q.isPending || q.isFetching);
  const failed = [detail, active, silence].some((q) => q.isError);
  const valid =
    detail.data?.id === board.id &&
    typeof active.data?.temporary_override?.active === "boolean" &&
    typeof silence.data?.active === "boolean";
  if (pending || failed || !valid)
    return (
      <StateDialog
        failed={!pending && (failed || !valid)}
        retry={() => {
          void detail.refetch();
          void active.refetch();
          void silence.refetch();
        }}
        onClose={onClose}
      />
    );
  const nameOf = (id: string | null | undefined) =>
    pages?.pages.find((p) => p.id === id)?.name ?? collections?.collections.find((c) => c.id === id)?.name ?? null;
  const override = active.data!.temporary_override;
  return (
    <ChangePageDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      board={{ ...board, paused: detail.data!.paused }}
      boardName={board.name}
      isPrimary={detail.data!.is_primary}
      scheduleEnabled={active.data!.schedule_enabled}
      currentPageId={override.active ? override.page_id : detail.data!.active_page_id}
      manualPageName={nameOf(detail.data!.active_page_id)}
      overrideName={override.active ? (nameOf(override.page_id) ?? tn("composedMessage")) : null}
      nextChange={override.active ? null : scheduleNextChange(detail.data, new Date())}
      silence={silence.data!.active ? { until: silenceEndsAtLabel(silence.data) } : null}
      initialPageId={collection.id}
    />
  );
}
