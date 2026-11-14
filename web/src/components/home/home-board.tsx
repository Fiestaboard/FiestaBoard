"use client";

import { type BoardCellGrid, DISPLAY_TYPE_LABELS, displayTypeForModel } from "@fiestaboard/ui";

import { DevicePreview } from "@/components/device-preview";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { resolveCode62Glyph } from "@/hooks/use-board";
import type { BoardInstance, CanvasLayerJson } from "@/lib/api";
import type { BoardGeometry } from "@/lib/board-characters-to-template";
import { resolveDimensions } from "@/lib/board-dimensions";
import { resolveBoardModel } from "@/lib/device-preview";

/** A display's geometry from its settings (the preview of something not yet on it). */
export function boardGeometry(board: BoardInstance | undefined): BoardGeometry {
  if (!board) return { deviceType: "flagship", notesWide: 1, notesTall: 1 };
  return {
    deviceType: board.device_type,
    notesWide: board.notes_wide ?? 1,
    notesTall: board.notes_tall ?? 1,
    gridRows: board.grid_rows ?? undefined,
    gridCols: board.grid_cols ?? undefined,
  };
}

/**
 * The Now showing header's mono meta: "Flagship 22 × 6" (CANON writes boards
 * COLUMNS × ROWS). The type name comes from FiestaUI's display types (1.5c);
 * an unknown model falls back to the size alone.
 */
export function boardMeta(board: BoardInstance | undefined, geometry: BoardGeometry): string {
  const dims = resolveDimensions(
    geometry.deviceType,
    geometry.notesWide,
    geometry.notesTall,
    geometry.gridRows,
    geometry.gridCols,
  );
  const size = `${dims.cols} × ${dims.rows}`;
  const model = resolveBoardModel(board);
  const type = model ? displayTypeForModel(model) : undefined;
  return type ? `${DISPLAY_TYPE_LABELS[type].label} ${size}` : size;
}

export interface HomeBoardProps {
  board: BoardInstance | undefined;
  geometry: BoardGeometry;
  message: string | null;
  cells?: BoardCellGrid;
  layers?: CanvasLayerJson[] | null;
  isLoading?: boolean;
  size?: "sm" | "md";
  /** Board colour and code-62 glyph when the display carries none of its own. */
  fallbackColor?: "black" | "white";
  fallbackGlyph?: "degree" | "heart";
  previewLabel?: string;
}

/**
 * One display, drawn the way it looks on the wall: an LED board as its LED
 * matrix, a split-flap board through the app's ScaledBoardDisplay wrapper
 * (2.4 swaps that wrapper onto BoardViewport; this file only passes props).
 */
export function HomeBoard({
  board,
  geometry,
  message,
  cells,
  layers,
  isLoading = false,
  size = "md",
  fallbackColor = "black",
  fallbackGlyph,
  previewLabel,
}: HomeBoardProps) {
  return (
    <DevicePreview
      model={resolveBoardModel(board)}
      ledLayout={board?.led_layout}
      message={message}
      cells={cells}
      layers={layers}
      size={size}
      previewLabel={previewLabel}
    >
      <ScaledBoardDisplay
        message={message}
        isLoading={isLoading}
        size={size}
        boardType={board?.board_color ?? fallbackColor}
        deviceType={geometry.deviceType}
        notesWide={geometry.notesWide}
        notesTall={geometry.notesTall}
        gridRows={geometry.gridRows}
        gridCols={geometry.gridCols}
        // Which code-62 flap this board carries (issue #1657).
        code62Glyph={resolveCode62Glyph(geometry.deviceType, board?.code62_glyph ?? fallbackGlyph)}
      />
    </DevicePreview>
  );
}
