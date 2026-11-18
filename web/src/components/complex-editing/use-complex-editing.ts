"use client";

import type { ZoomValue } from "@fiestaboard/ui";
import { useState } from "react";

import { useBoardViewportScroll } from "@/hooks/use-board-viewport-scroll";
import { isBigBoard } from "@/lib/complex-editing";

export interface ComplexEditingOptions {
  rows: number;
  cols: number;
  deviceType: string;
  notesWide: number;
  notesTall: number;
  /**
   * The desktop pane editor (≥1024 px) on a split-flap preview. 04b draws the
   * ruler, minimap, zoom, Go to, truncation map, bands and Note focus only at
   * desktop; the 900 and 390 frames scroll the docked preview instead (DD-W).
   */
  enabled: boolean;
  /** The element around the preview board, measured for the ruler, minimap and seams. */
  stage: HTMLElement | null;
}

/**
 * Editor-local state for the 04b complex-editing lenses. Nothing here changes
 * the page: zoom, the minimap, Note focus and the measured preview viewport.
 */
export function useComplexEditing({
  rows,
  cols,
  deviceType,
  notesWide,
  notesTall,
  enabled,
  stage,
}: ComplexEditingOptions) {
  const bigBoard = enabled && isBigBoard({ rows, cols });
  const noteArray = enabled && deviceType === "note_array" && notesWide * notesTall > 1;
  // 04b `126:149604` opens a big board at Tile sm, the editable floor.
  const [zoom, setZoom] = useState<ZoomValue>("sm");
  const [minimapOpen, setMinimapOpen] = useState(true);
  const [focusedNote, setFocusedNote] = useState<number | null>(null);
  const viewport = useBoardViewportScroll(stage, cols, bigBoard || noteArray);
  // A resized array keeps the focus only while that Note still exists.
  const note = noteArray && focusedNote !== null && focusedNote <= notesWide * notesTall ? focusedNote : null;

  return {
    active: bigBoard || noteArray,
    bigBoard,
    noteArray,
    rows,
    cols,
    notesWide,
    notesTall,
    zoom,
    setZoom,
    /** The preview's mode and tile size while the zoom control owns them. */
    previewMode: zoom === "fit" ? ("fit" as const) : ("actual" as const),
    previewSize: zoom === "fit" ? ("sm" as const) : zoom,
    minimapOpen,
    setMinimapOpen,
    note,
    setNote: setFocusedNote,
    geometry: viewport.geometry,
    scrollToColumn: viewport.scrollToColumn,
  };
}

export type ComplexEditing = ReturnType<typeof useComplexEditing>;
