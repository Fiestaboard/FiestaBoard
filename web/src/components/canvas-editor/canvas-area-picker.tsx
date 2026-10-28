"use client";

// Drag across the page's character grid to choose a canvas's area. Every
// canvas shows as a labelled outline; the one being edited is filled. The
// row / column fields beside it are the keyboard way to do the same.

import { Box, Text } from "@fiestaboard/ui";
import { useEffect, useId, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { Canvas, CanvasArea } from "@/lib/api";
import { clampArea } from "@/lib/canvas-editing";

const CELL = 18;

interface CanvasAreaPickerProps {
  rows: number;
  cols: number;
  canvases: Canvas[];
  activeId: string;
  onAreaChange: (area: CanvasArea) => void;
}

/** The area spanned by two 0-based cells, as a 1-based canvas area. */
export function areaBetween(a: { r: number; c: number }, b: { r: number; c: number }): CanvasArea {
  const r0 = Math.min(a.r, b.r);
  const c0 = Math.min(a.c, b.c);
  return { row: r0 + 1, col: c0 + 1, rows: Math.abs(a.r - b.r) + 1, cols: Math.abs(a.c - b.c) + 1 };
}

export function CanvasAreaPicker({ rows, cols, canvases, activeId, onAreaChange }: CanvasAreaPickerProps) {
  const t = useTranslations("canvasEditor");
  const ref = useRef<HTMLCanvasElement>(null);
  const [drag, setDrag] = useState<{ start: { r: number; c: number }; end: { r: number; c: number } } | null>(null);
  const hintId = useId();

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext?.("2d");
    if (!canvas || !ctx) return;
    canvas.width = cols * CELL;
    canvas.height = rows * CELL;
    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    for (let c = 0; c <= cols; c++) ctx.strokeRect(c * CELL + 0.5, 0, 0, rows * CELL);
    for (let r = 0; r <= rows; r++) ctx.strokeRect(0, r * CELL + 0.5, cols * CELL, 0);
    for (const cv of canvases) {
      const area = clampArea(drag && cv.id === activeId ? areaBetween(drag.start, drag.end) : cv.area, rows, cols);
      if (!area) continue;
      const x = (area.col - 1) * CELL;
      const y = (area.row - 1) * CELL;
      const w = area.cols * CELL;
      const h = area.rows * CELL;
      const active = cv.id === activeId;
      if (active) {
        ctx.fillStyle = "rgba(99,102,241,0.35)";
        ctx.fillRect(x, y, w, h);
      }
      ctx.strokeStyle = active ? "#818cf8" : "#a3a3a3";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);
      ctx.fillStyle = "#ffffff";
      ctx.font = "10px sans-serif";
      ctx.fillText(cv.id, x + 3, y + 11);
    }
  }, [rows, cols, canvases, activeId, drag]);

  const cellAt = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = rect.width ? (cols * CELL) / rect.width : 1;
    const scaleY = rect.height ? (rows * CELL) / rect.height : 1;
    const c = Math.floor(((e.clientX - rect.left) * scaleX) / CELL);
    const r = Math.floor(((e.clientY - rect.top) * scaleY) / CELL);
    return { r: Math.min(rows - 1, Math.max(0, r)), c: Math.min(cols - 1, Math.max(0, c)) };
  };

  return (
    <Box>
      <canvas
        ref={ref}
        role="img"
        aria-label={t("areaPickerLabel")}
        aria-describedby={hintId}
        data-testid="canvas-area-picker"
        width={cols * CELL}
        height={rows * CELL}
        style={{ aspectRatio: `${cols} / ${rows}`, touchAction: "none" }}
        className="block w-full max-w-md cursor-crosshair rounded border"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture?.(e.pointerId);
          const cell = cellAt(e);
          setDrag({ start: cell, end: cell });
        }}
        onPointerMove={(e) => {
          if (drag) setDrag({ ...drag, end: cellAt(e) });
        }}
        onPointerUp={(e) => {
          if (!drag) return;
          onAreaChange(areaBetween(drag.start, cellAt(e)));
          setDrag(null);
        }}
      />
      <Text id={hintId} size="xs" tone="muted" className="mt-1">
        {t("areaPickerHint")}
      </Text>
    </Box>
  );
}
