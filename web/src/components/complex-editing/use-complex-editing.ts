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
  /**
   * Draw mode: the lenses step aside, but a big board keeps the zoom it had,
   * so the overview carries into draw mode (`ownsZoom`).
   */
  paused?: boolean;
  /** The element around the preview board, measured for the ruler, minimap and seams. */
  stage: HTMLElement | null;
  /**
   * The session's Fit / Actual preference (2.5). The zoom starts from it and
   * reports Fit-or-not back, so leaving the lenses (draw mode, a narrower
   * window) keeps the overview the user chose.
   */
  previewMode?: "fit" | "actual";
  onPreviewModeChange?: (mode: "fit" | "actual") => void;
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
  paused = false,
  stage,
  previewMode: sessionMode = "actual",
  onPreviewModeChange,
}: ComplexEditingOptions) {
  const ownsZoom = enabled && isBigBoard({ rows, cols });
  const bigBoard = ownsZoom && !paused;
  const noteArray = enabled && !paused && deviceType === "note_array" && notesWide * notesTall > 1;
  // A big board opens at Fit (UX-4-2, DD-W156): 04b `126:149604`'s Tile sm
  // opened Den TV cropped at column 28 when Fit shows all 34. Actual size
  // uses the last tile size chosen (Tile sm until one is).
  const [zoom, setZoomState] = useState<ZoomValue>("fit");
  const [tile, setTile] = useState<"sm" | "md" | "lg">("sm");
  const setZoom = (next: ZoomValue) => {
    setZoomState(next);
    if (next !== "fit") setTile(next);
    const mode = next === "fit" ? "fit" : "actual";
    if (mode !== sessionMode) onPreviewModeChange?.(mode);
  };
  // The ruler is off by default except over a note array, where it marks the
  // Note seams (DD-W131); the View menu turns it on (UX-4-2).
  const [rulerOpen, setRulerOpen] = useState(() => deviceType === "note_array");
  const [focusedNote, setFocusedNote] = useState<number | null>(null);
  const viewport = useBoardViewportScroll(stage, cols, bigBoard || noteArray);
  // A resized array keeps the focus only while that Note still exists.
  const note = noteArray && focusedNote !== null && focusedNote <= notesWide * notesTall ? focusedNote : null;

  return {
    active: bigBoard || noteArray,
    bigBoard,
    /** A big board on the desktop pane, in draw mode too: the preview's mode and size follow the zoom. */
    ownsZoom,
    noteArray,
    rows,
    cols,
    notesWide,
    notesTall,
    zoom,
    setZoom,
    /** The tile size Actual size uses. */
    tile,
    /** Fit, or Actual size at the last tile size. */
    setMode: (mode: "fit" | "actual") => setZoom(mode === "fit" ? "fit" : tile),
    /** The preview's mode and tile size while the zoom control owns them. */
    previewMode: zoom === "fit" ? ("fit" as const) : ("actual" as const),
    previewSize: zoom === "fit" ? ("sm" as const) : zoom,
    rulerOpen,
    setRulerOpen,
    note,
    setNote: setFocusedNote,
    geometry: viewport.geometry,
    scrollToColumn: viewport.scrollToColumn,
  };
}

export type ComplexEditing = ReturnType<typeof useComplexEditing>;
