import { useCurrentBoard } from "@/components/current-board-context";
import { ChangePageDialog } from "@/components/home/change-page-dialog";
import { scheduleNextChange } from "@/components/home/home-status";
import { useBoardDetail } from "@/components/home/use-home-data";
import { useBoardSettings, usePages } from "@/hooks/use-board";
import { useSilence } from "@/hooks/use-silence";
import type { Collection } from "@/lib/api";

/** Show the saved Collection on the display explicitly named by the shared dialog. */
export function CollectionShowNow({ collection, onClose }: { collection: Collection; onClose: () => void }) {
  const { currentBoard, boards } = useCurrentBoard();
  const settings = useBoardSettings();
  const allBoards = boards.length ? boards : (settings.data?.boards ?? []);
  const board = currentBoard ?? allBoards[0];
  const scopedId = allBoards.length > 1 ? board?.id : undefined;
  const { data: detail } = useBoardDetail(scopedId);
  const silence = useSilence(scopedId);
  const { data: pages } = usePages();
  const manualName = pages?.pages.find((p) => p.id === detail?.active_page_id)?.name ?? null;
  return (
    <ChangePageDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      board={board}
      boardName={board?.name}
      isPrimary={!board || board.id === allBoards[0]?.id}
      scheduleEnabled={board?.schedule_enabled ?? detail?.schedule_enabled ?? false}
      currentPageId={detail?.active_page_id}
      manualPageName={manualName}
      overrideName={detail?.override_started_at || detail?.override_expires_at ? (manualName ?? collection.name) : null}
      nextChange={scheduleNextChange(detail, new Date())}
      silence={silence.active ? { until: silence.until } : null}
      initialPageId={collection.id}
    />
  );
}
