"use client";

import { useState } from "react";

import { ComposePageDialog } from "@/components/compose-page-dialog";
import { useCurrentBoard } from "@/components/current-board-context";
import {
  getEffectiveBoardColor,
  getEffectiveCode62Glyph,
  getEffectiveDeviceType,
  resolveCode62Glyph,
  useBoardSettings,
  usePages,
} from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useSilence } from "@/hooks/use-silence";
import { resolveBoardModel } from "@/lib/device-preview";

import { boardGeometry, boardMeta } from "./home-board";
import { scheduleNextChange } from "./home-status";
import { useBoardDetail } from "./use-home-data";

/**
 * Compose a message, opened from the PageHeader (the one entry), the board
 * menu or C. "Show on" defaults to the display in the switcher; since H1
 * every display has its own override, so the message goes where it says.
 */
export function HomeCompose({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { currentBoardId, boards } = useCurrentBoard();
  const { data: boardSettings } = useBoardSettings();
  const allBoards = boards.length > 0 ? boards : (boardSettings?.boards ?? []);
  // null follows the display in the switcher; a Show on pick overrides it.
  const [targetId, setTargetId] = useState<string | null>(null);

  // Each opening starts on the display in the switcher.
  if (useDepsChanged([open]) && open) {
    setTargetId(null);
  }

  const target = allBoards.find((b) => b.id === (targetId ?? currentBoardId)) ?? allBoards[0];
  // Board-scoped reads only in a multi-display install, as elsewhere on Home.
  const scopedId = allBoards.length > 1 ? target?.id : undefined;
  const silence = useSilence(scopedId);
  const { data: detail } = useBoardDetail(scopedId);
  const { data: pagesData } = usePages();

  const deviceType = target?.device_type ?? getEffectiveDeviceType(boardSettings);
  const scheduleEnabled = target?.schedule_enabled ?? detail?.schedule_enabled ?? false;
  const overrideActive = !!detail?.override_expires_at || detail?.override_started_at != null;
  const nextChange = overrideActive ? null : scheduleNextChange(detail, new Date());
  const nextPageName = nextChange?.pageId
    ? (pagesData?.pages?.find((p) => p.id === nextChange.pageId)?.name ?? null)
    : null;

  return (
    <ComposePageDialog
      open={open}
      onOpenChange={onOpenChange}
      deviceType={deviceType}
      notesWide={target?.notes_wide ?? 1}
      notesTall={target?.notes_tall ?? 1}
      gridRows={target?.grid_rows}
      gridCols={target?.grid_cols}
      model={resolveBoardModel(target)}
      ledLayout={target?.led_layout}
      boardColor={target?.board_color ?? getEffectiveBoardColor(boardSettings)}
      code62Glyph={resolveCode62Glyph(deviceType, target?.code62_glyph ?? getEffectiveCode62Glyph(boardSettings))}
      targetBoardId={target?.id}
      targetBoardLabel={target?.name}
      // H1: always name the display (review S7).
      sendBoardId={target?.id}
      showsCapitals={detail?.drawing?.features?.lowercase === false}
      showOn={
        allBoards.length > 0
          ? {
              value: target?.id ?? "",
              onValueChange: setTargetId,
              // 07a: "Kitchen board · Flagship 22 × 6".
              options: allBoards.map((b) => ({ id: b.id, label: `${b.name} · ${boardMeta(b, boardGeometry(b))}` })),
            }
          : undefined
      }
      scheduleEnabled={scheduleEnabled}
      nextChange={nextChange}
      nextPageName={nextPageName}
      silence={silence.active ? { until: silence.until, holds: silence.holds } : null}
    />
  );
}
