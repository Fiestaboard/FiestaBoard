"use client";

import { BoardMinimap, type BoardMinimapProps, Box, ColumnRuler, NoteSeams } from "@fiestaboard/ui";

import type { ComplexEditing } from "@/components/complex-editing/use-complex-editing";
import { useTranslations } from "@/i18n/translations";

/** Kit ColumnRuler draws column 1's tick 14 px in from its own left edge. */
const RULER_TICK_INSET = 14;

/** The ruler above the preview board (big boards): it follows the board's scroll. */
export function ComplexPreviewRuler({ complex }: { complex: ComplexEditing }) {
  const t = useTranslations("complexEditing");
  const { geometry, bigBoard, cols } = complex;
  if (!bigBoard || !complex.rulerOpen || geometry.pitch <= 0) return null;
  const left = geometry.originX + (geometry.first - 1) * geometry.pitch + geometry.tileWidth / 2 - RULER_TICK_INSET;
  return (
    <Box className="overflow-hidden" data-slot="complex-preview-ruler">
      <ColumnRuler
        columns={cols}
        columnPitch={geometry.pitch}
        visibleRange={{ start: geometry.first, end: geometry.last }}
        marks={[{ id: "cut", type: "cut", column: cols, label: t("cutMark") }]}
        label={t("rulerLabel", { columns: cols })}
        style={{ marginLeft: left }}
      />
    </Box>
  );
}

/**
 * Note seams and the focused Note's outline over a note array's preview.
 * Render inside the (relative) element the editor measures as its stage.
 */
export function ComplexPreviewSeams({ complex }: { complex: ComplexEditing }) {
  const { geometry, noteArray, notesWide, notesTall, note } = complex;
  if (!noteArray || geometry.pitch <= 0 || !geometry.clip) return null;
  return (
    <Box
      aria-hidden="true"
      data-slot="complex-preview-seams"
      className="pointer-events-none absolute overflow-hidden"
      style={{ left: geometry.clip.x, top: geometry.clip.y, width: geometry.clip.width, height: geometry.clip.height }}
    >
      <NoteSeams
        notesWide={notesWide}
        notesTall={notesTall}
        tileWidth={geometry.tileWidth}
        tileHeight={geometry.tileHeight}
        columnGap={geometry.columnGap}
        rowGap={geometry.rowGap}
        seamGap={geometry.seamGap}
        note={note}
        style={{
          position: "absolute",
          left: geometry.originX - geometry.clip.x,
          top: geometry.originY - geometry.clip.y,
        }}
      />
    </Box>
  );
}

export interface ComplexPreviewOverviewProps {
  complex: ComplexEditing;
  /** The overview's board: the preview's own message and geometry. */
  board: BoardMinimapProps["board"];
  minimapId: string;
}

/**
 * Below a big board's preview: the minimap that pans it, only while the zoom
 * crops the board (UX-4-2). At Fit the whole board is already in view, and
 * where lines are cut is the H4 card's and the cut marker's to say (UX-4-3).
 */
export function ComplexPreviewOverview({ complex, board, minimapId }: ComplexPreviewOverviewProps) {
  const t = useTranslations("complexEditing");
  const { geometry, bigBoard, cols, rows } = complex;
  const cropped = geometry.pitch > 0 && (geometry.first > 1 || geometry.last < cols);
  if (!bigBoard || complex.zoom === "fit" || !cropped) return null;
  return (
    <Box data-slot="complex-preview-overview" className="min-w-0">
      <BoardMinimap
        id={minimapId}
        className="w-[282px] max-w-full"
        board={board}
        viewport={{ column: geometry.first, row: 1, columns: geometry.last - geometry.first + 1, rows }}
        onJump={({ column }) => complex.scrollToColumn(column)}
        labels={{
          control: t("minimapControl"),
          overview: (c, r) => t("minimapOverview", { columns: c, rows: r }),
          viewport: (firstColumn, lastColumn, firstRow, lastRow) =>
            t("minimapViewport", { firstColumn, lastColumn, firstRow, lastRow }),
          hint: t("minimapHint"),
          keyboard: t("minimapKeyboard"),
        }}
      />
    </Box>
  );
}
