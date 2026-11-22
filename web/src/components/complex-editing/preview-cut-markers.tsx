// H4 cut marker (07c `307:41698`): a dashed outline on the preview tile where
// a line the hub measured too long is cut, with "+2 cut off" under it. The
// overflow card says the same in words; this shows where (BB-E-10).
// Geometry comes from the board's own tiles (`emitCellMetadata`), as Inspect's
// outline does, so it follows any scale, layout or scroll.
// TODO(FiestaUI): a BoardDisplay `highlightCells` slot would own this (DD-W row).

"use client";

import { Box, Text } from "@fiestaboard/ui";
import { useLayoutEffect, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { LineOverflow } from "@/lib/complex-editing";

interface Marker {
  line: number;
  cut: number;
  top: number;
  left: number;
  width: number;
  height: number;
}

/** The last tile of each cut row, as `[row, col]`, 0-based. Wrapped lines are never cut. */
export function cutCells(
  overflows: readonly LineOverflow[],
  rows: number,
  cols: number,
  wrapped: readonly boolean[],
): { line: number; cut: number; row: number; col: number }[] {
  return overflows
    .filter((overflow) => overflow.line <= rows && !wrapped[overflow.line - 1])
    .map((overflow) => ({ line: overflow.line, cut: overflow.cut, row: overflow.line - 1, col: cols - 1 }));
}

function measure(stage: HTMLElement, cells: ReturnType<typeof cutCells>): Marker[] {
  const base = stage.getBoundingClientRect();
  const markers: Marker[] = [];
  for (const cell of cells) {
    const tile = stage.querySelector<HTMLElement>(`[data-row="${cell.row}"][data-col="${cell.col}"]`);
    if (!tile) continue;
    const rect = tile.getBoundingClientRect();
    // A board scrolled sideways may have the cut tile out of view: no marker over other tiles.
    const view = tile.closest<HTMLElement>('[data-slot="board-viewport-scroller"]')?.getBoundingClientRect();
    if (view && (rect.right > view.right + 1 || rect.left < view.left - 1)) continue;
    markers.push({
      line: cell.line,
      cut: cell.cut,
      top: rect.top - base.top,
      left: rect.left - base.left,
      width: rect.width,
      height: rect.height,
    });
  }
  return markers;
}

export function PreviewCutMarkers({
  stage,
  overflows,
  rows,
  cols,
  wrapped,
}: {
  /** The preview's positioned stage, which holds the board's tiles. */
  stage: HTMLElement | null;
  overflows: readonly LineOverflow[];
  rows: number;
  cols: number;
  wrapped: readonly boolean[];
}) {
  const t = useTranslations("complexEditing");
  const [markers, setMarkers] = useState<Marker[]>([]);
  const key = JSON.stringify(cutCells(overflows, rows, cols, wrapped));

  useLayoutEffect(() => {
    const cells = JSON.parse(key) as ReturnType<typeof cutCells>;
    if (!stage || cells.length === 0) return;
    const update = () => {
      const next = measure(stage, cells);
      setMarkers((current) => (JSON.stringify(current) === JSON.stringify(next) ? current : next));
    };
    update();
    // Tiles land after the board renders, and the viewport scrolls sideways.
    const resize = new ResizeObserver(update);
    resize.observe(stage);
    const mutation = new MutationObserver(update);
    mutation.observe(stage, { childList: true, subtree: true });
    stage.addEventListener("scroll", update, { capture: true, passive: true });
    return () => {
      resize.disconnect();
      mutation.disconnect();
      stage.removeEventListener("scroll", update, { capture: true });
    };
  }, [stage, key]);

  // Nothing is cut (any more): the last measurement no longer applies.
  const shown = stage && key !== "[]" ? markers : [];
  return (
    <>
      {shown.map((marker, index) => (
        <Box
          key={marker.line}
          aria-hidden
          data-testid="preview-cut-marker"
          className="pointer-events-none absolute z-10 rounded-sm border-2 border-dashed border-destructive"
          style={{
            top: marker.top - 3,
            left: marker.left - 3,
            width: marker.width + 6,
            height: marker.height + 6,
          }}
        >
          {/* One badge, on the first cut: on consecutive rows more would cover the tiles below. */}
          {index === 0 && (
            <Text
              as="span"
              size="xs"
              weight="medium"
              className="absolute right-0 top-full mt-1 whitespace-nowrap rounded-sm bg-destructive px-1.5 py-0.5 text-destructive-foreground"
            >
              {t("cutMarker", { count: marker.cut })}
            </Text>
          )}
        </Box>
      ))}
    </>
  );
}
