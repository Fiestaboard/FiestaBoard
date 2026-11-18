// Inspect (04c C3): outlines the rows a token fills (dashed) and the clicked
// tile (solid) over the preview board. Geometry comes from the board's own
// tiles (`emitCellMetadata`), so the outline follows any scale or layout.
// TODO(FiestaUI): a BoardDisplay `highlightCells` slot would own this (DD-W row).

"use client";

import { Box } from "@fiestaboard/ui";
import { type RefObject, useLayoutEffect, useState } from "react";

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface BoardCellHighlightProps {
  containerRef: RefObject<HTMLDivElement | null>;
  /** 0-based [row, col] cells from the same source. */
  cells: ReadonlyArray<readonly [number, number]>;
  selected: readonly [number, number];
}

function measure(container: HTMLElement, cells: ReadonlyArray<readonly [number, number]>): Rect | null {
  const base = container.getBoundingClientRect();
  let rect: { top: number; left: number; right: number; bottom: number } | null = null;
  for (const [row, col] of cells) {
    const tile = container.querySelector<HTMLElement>(`[data-row="${row}"][data-col="${col}"]`);
    if (!tile) continue;
    const r = tile.getBoundingClientRect();
    rect = rect
      ? {
          top: Math.min(rect.top, r.top),
          left: Math.min(rect.left, r.left),
          right: Math.max(rect.right, r.right),
          bottom: Math.max(rect.bottom, r.bottom),
        }
      : { top: r.top, left: r.left, right: r.right, bottom: r.bottom };
  }
  if (!rect) return null;
  return {
    top: rect.top - base.top,
    left: rect.left - base.left,
    width: rect.right - rect.left,
    height: rect.bottom - rect.top,
  };
}

export function BoardCellHighlight({ containerRef, cells, selected }: BoardCellHighlightProps) {
  const [rects, setRects] = useState<{ band: Rect | null; cell: Rect | null }>({ band: null, cell: null });

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const update = () => setRects({ band: measure(container, cells), cell: measure(container, [selected]) });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  }, [containerRef, cells, selected]);

  const style = (rect: Rect) => ({
    top: rect.top - 3,
    left: rect.left - 3,
    width: rect.width + 6,
    height: rect.height + 6,
  });
  return (
    <>
      {rects.band && (
        <Box
          aria-hidden
          data-testid="inspect-band"
          className="pointer-events-none absolute rounded-md border-2 border-dashed border-ring"
          style={style(rects.band)}
        />
      )}
      {rects.cell && (
        <Box
          aria-hidden
          data-testid="inspect-cell"
          className="pointer-events-none absolute rounded-sm border-2 border-ring"
          style={style(rects.cell)}
        />
      )}
    </>
  );
}
