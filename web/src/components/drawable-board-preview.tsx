"use client";

/**
 * Wraps the board preview with a single delegated pointer listener that
 * turns clicks/drags over tiles into paint strokes. Hit-testing uses the
 * tiles' data-row/data-col attributes via elementFromPoint, so
 * ScaledBoardDisplay's CSS transform never enters coordinate math.
 */

import { useCallback, useEffect, useRef } from "react";
import type { ReactNode } from "react";

export interface StrokeCell {
  row: number;
  col: number;
}

interface DrawableBoardPreviewProps {
  active: boolean;
  onStrokePreview: (cells: StrokeCell[]) => void;
  onStrokeCommit: (cells: StrokeCell[]) => void;
  children: ReactNode;
}

function cellAtPoint(x: number, y: number): StrokeCell | null {
  const el = document.elementFromPoint(x, y);
  const tile = el?.closest?.("[data-row][data-col]") as HTMLElement | null;
  if (!tile) return null;
  const row = Number(tile.dataset.row);
  const col = Number(tile.dataset.col);
  if (!Number.isInteger(row) || !Number.isInteger(col)) return null;
  return { row, col };
}

export function DrawableBoardPreview({ active, onStrokePreview, onStrokeCommit, children }: DrawableBoardPreviewProps) {
  const strokeRef = useRef<Map<string, StrokeCell> | null>(null);
  const rafRef = useRef<number | null>(null);

  const flushPreview = useCallback(() => {
    rafRef.current = null;
    if (strokeRef.current) onStrokePreview([...strokeRef.current.values()]);
  }, [onStrokePreview]);

  const schedulePreview = useCallback(() => {
    if (rafRef.current === null) rafRef.current = requestAnimationFrame(flushPreview);
  }, [flushPreview]);

  const abortStroke = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (strokeRef.current) {
      strokeRef.current = null;
      onStrokePreview([]);
    }
  }, [onStrokePreview]);

  // Leaving draw mode mid-stroke must not leave a dangling stroke.
  useEffect(() => {
    if (!active) abortStroke();
  }, [active, abortStroke]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!active || e.button !== 0) return;
    const cell = cellAtPoint(e.clientX, e.clientY);
    if (!cell) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    strokeRef.current = new Map([[`${cell.row}:${cell.col}`, cell]]);
    schedulePreview();
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!strokeRef.current) return;
    const cell = cellAtPoint(e.clientX, e.clientY);
    if (!cell) return;
    const key = `${cell.row}:${cell.col}`;
    if (!strokeRef.current.has(key)) {
      strokeRef.current.set(key, cell);
      schedulePreview();
    }
  };

  const handlePointerUp = () => {
    if (!strokeRef.current) return;
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const cells = [...strokeRef.current.values()];
    strokeRef.current = null;
    onStrokeCommit(cells);
  };

  return (
    <div
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={abortStroke}
      className={active ? "cursor-crosshair select-none" : undefined}
      style={active ? { touchAction: "none" } : undefined}
      data-draw-surface={active ? "true" : undefined}
    >
      {children}
    </div>
  );
}
