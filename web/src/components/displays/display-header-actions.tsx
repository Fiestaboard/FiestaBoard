"use client";

import { Button } from "@fiestaboard/ui";
import { Pause, Play } from "lucide-react";
import { useState } from "react";

import { ChangePageDialog } from "@/components/home/change-page-dialog";
import { scheduleNextChange } from "@/components/home/home-status";
import { useBoardDetail } from "@/components/home/use-home-data";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { useTranslations } from "@/i18n/translations";
import type { BoardInstance } from "@/lib/api";

/**
 * 07d `320:18175` / `320:9461`: "Change Page…" in a display's header, opening
 * the same Change Page flow as Home for this display.
 */
export function DisplayChangePageButton({ board }: { board: BoardInstance }) {
  const t = useTranslations("displays.fleet");
  const displays = useDisplayBoards();
  const { data: detail } = useBoardDetail(board.id);
  const [changing, setChanging] = useState(false);
  return (
    <>
      <Button variant="outline" onClick={() => setChanging(true)}>
        {t("changePage")}
      </Button>
      {changing && (
        <ChangePageDialog
          open={changing}
          onOpenChange={setChanging}
          board={board}
          isPrimary={displays.boards[0]?.id === board.id}
          scheduleEnabled={detail?.schedule_enabled ?? board.schedule_enabled ?? false}
          currentPageId={detail?.resolved_page_id}
          nextChange={scheduleNextChange(detail, new Date())}
        />
      )}
    </>
  );
}

/**
 * 07d `320:18175`: Pause beside Change Page… in the display's header; a
 * paused display offers Resume. The same pause as Overview's switch.
 */
export function DisplayPauseButton({ board }: { board: BoardInstance }) {
  const t = useTranslations("displays.fleet");
  const displays = useDisplayBoards();
  const paused = board.paused === true;
  return (
    <Button variant="outline" disabled={displays.pausePending} onClick={() => displays.setPaused(board.id, !paused)}>
      {paused ? <Play className="size-4" aria-hidden="true" /> : <Pause className="size-4" aria-hidden="true" />}
      {paused ? t("resume") : t("pause")}
    </Button>
  );
}
