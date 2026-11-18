"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Reads and drives the editor preview's FiestaUI `BoardViewport` from outside
 * (web 2.9: ruler, minimap, Go to and Note seams follow the scroll).
 *
 * The kit viewport owns its scroll and exposes no controlled position, so the
 * host measures the tiles it already renders with `emitCellMetadata`
 * (`data-row` / `data-col`) inside the published `data-slot` parts. FiestaUI
 * follow-up: a controlled `scrollColumn` / `onVisibleRangeChange` API (DD-W).
 */
export interface BoardViewportGeometry {
  /** One-based visible column range. */
  first: number;
  last: number;
  /** Tile width plus gutter, in px. Zero until measured. */
  pitch: number;
  /** The first tile's top-left, relative to the stage. */
  originX: number;
  originY: number;
  tileWidth: number;
  tileHeight: number;
  columnGap: number;
  rowGap: number;
  /** Extra space at a Note seam (note arrays), in px. */
  seamGap: number;
  /** The scroller's box, relative to the stage: what the board shows. */
  clip: { x: number; y: number; width: number; height: number } | null;
}

const SCROLLER = '[data-slot="board-viewport-scroller"]';

function tile(root: Element, row: number, col: number): Element | null {
  return root.querySelector(`[data-row="${row}"][data-col="${col}"]`);
}

/** Measure the stage's board. Exported for tests: JSDOM has no layout. */
export function measureBoardViewport(stage: Element, columns: number): BoardViewportGeometry {
  const scroller = stage.querySelector(SCROLLER);
  const first = tile(stage, 0, 0);
  const stageRect = stage.getBoundingClientRect();
  const empty: BoardViewportGeometry = {
    first: 1,
    last: columns,
    pitch: 0,
    originX: 0,
    originY: 0,
    tileWidth: 0,
    tileHeight: 0,
    columnGap: 0,
    rowGap: 0,
    seamGap: 0,
    clip: null,
  };
  if (!first) return empty;
  const a = first.getBoundingClientRect();
  const b = tile(stage, 0, 1)?.getBoundingClientRect();
  const below = tile(stage, 1, 0)?.getBoundingClientRect();
  const beforeSeam = tile(stage, 0, 14)?.getBoundingClientRect();
  const afterSeam = tile(stage, 0, 15)?.getBoundingClientRect();
  const tileWidth = a.width;
  const columnGap = b ? Math.max(0, b.left - a.right) : 0;
  const pitch = b ? b.left - a.left : tileWidth;
  if (pitch <= 0) return empty;
  const view = scroller?.getBoundingClientRect() ?? stageRect;
  const seamGap = beforeSeam && afterSeam ? Math.max(0, afterSeam.left - beforeSeam.right - columnGap) : 0;
  // Columns whose tiles start inside the scroller's visible box.
  const firstVisible = Math.min(columns, Math.max(1, Math.ceil((view.left - a.left) / pitch - 0.01) + 1));
  const lastVisible = Math.min(columns, Math.max(firstVisible, Math.floor((view.right - a.left + columnGap) / pitch)));
  return {
    first: firstVisible,
    last: lastVisible,
    pitch,
    originX: a.left - stageRect.left,
    originY: a.top - stageRect.top,
    tileWidth,
    tileHeight: a.height,
    columnGap,
    rowGap: below ? Math.max(0, below.top - a.bottom) : columnGap,
    seamGap,
    clip: { x: view.left - stageRect.left, y: view.top - stageRect.top, width: view.width, height: view.height },
  };
}

function sameGeometry(a: BoardViewportGeometry, b: BoardViewportGeometry): boolean {
  return (Object.keys(a) as (keyof BoardViewportGeometry)[]).every((key) =>
    key === "clip" ? JSON.stringify(a.clip) === JSON.stringify(b.clip) : a[key] === b[key],
  );
}

/** `stage` is the element around the preview board (a callback-ref target). */
export function useBoardViewportScroll(stage: HTMLElement | null, columns: number, enabled = true) {
  const [geometry, setGeometry] = useState<BoardViewportGeometry>(() => ({
    first: 1,
    last: columns,
    pitch: 0,
    originX: 0,
    originY: 0,
    tileWidth: 0,
    tileHeight: 0,
    columnGap: 0,
    rowGap: 0,
    seamGap: 0,
    clip: null,
  }));

  useEffect(() => {
    if (!enabled || !stage) return;
    let frame = 0;
    let scroller: Element | null = null;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next = measureBoardViewport(stage, columns);
        setGeometry((previous) => (sameGeometry(previous, next) ? previous : next));
      });
    };
    const attach = () => {
      const current = stage.querySelector(SCROLLER);
      if (current === scroller) return;
      scroller?.removeEventListener("scroll", update);
      scroller = current;
      scroller?.addEventListener("scroll", update, { passive: true });
    };
    attach();
    update();
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    resize?.observe(stage);
    // The viewport remounts its scroller when the mode or size changes.
    const mutations = new MutationObserver(() => {
      attach();
      update();
    });
    mutations.observe(stage, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      scroller?.removeEventListener("scroll", update);
      resize?.disconnect();
      mutations.disconnect();
    };
  }, [stage, columns, enabled]);

  /** Bring a one-based column to the viewport's leading edge (the kit snaps it to a column). */
  const scrollToColumn = useCallback(
    (column: number) => {
      const scroller = stage?.querySelector<HTMLElement>(SCROLLER);
      const target = stage && tile(stage, 0, Math.max(0, Math.min(columns, column) - 1));
      const origin = stage && tile(stage, 0, 0);
      if (!scroller || !target || !origin) return;
      const offset = target.getBoundingClientRect().left - origin.getBoundingClientRect().left;
      scroller.scrollTo({ left: offset, behavior: "auto" });
    },
    [stage, columns],
  );

  return { geometry, scrollToColumn };
}
