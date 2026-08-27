"use client";

import { BoardDisplay, Box, type Code62Glyph, type DeviceType } from "@fiestaboard/ui";
import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { NOTE_COL_PITCH_IN, PANEL_PHYSICAL_WIDTH_IN, panelAutofitScale } from "@/lib/panel-scale";

interface PanelBoardProps {
  message: string | null;
  deviceType: DeviceType;
  notesWide: number;
  notesTall: number;
  rows: number;
  cols: number;
  boardColor: "black" | "white";
  code62Glyph: Code62Glyph;
  diagonalInches: number;
  calibration: number;
}

interface GridRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Transform-free offset of `el` relative to the positioned `container`. */
function offsetWithin(el: HTMLElement, container: HTMLElement): { x: number; y: number } {
  let x = 0;
  let y = 0;
  let node: HTMLElement | null = el;
  while (node && node !== container) {
    x += node.offsetLeft;
    y += node.offsetTop;
    node = node.offsetParent as HTMLElement | null;
  }
  return { x, y };
}

/** Physical column pitch in inches for the board's device family. */
function colPitchIn(deviceType: DeviceType): number {
  // Auto-fit grids are built from Note blocks; a legacy flagship panel
  // anchors to the Flagship's 41.2" / 22 columns instead.
  if (deviceType === "flagship") return PANEL_PHYSICAL_WIDTH_IN.flagship / 22;
  return NOTE_COL_PITCH_IN;
}

/**
 * Borderless board at true flap scale.
 *
 * The package board is rendered normally, then cropped to its tile grid
 * (bezel and padding fall outside an overflow-hidden window) and scaled so
 * each flap lands at real-world size — with a gentle ≤10% stretch toward
 * the nearest screen edge (see panelAutofitScale). Measurement uses
 * offset* geometry, which ignores CSS transforms, so the scale never feeds
 * back into itself.
 */
export function PanelBoard({
  message,
  deviceType,
  notesWide,
  notesTall,
  rows,
  cols,
  boardColor,
  code62Glyph,
  diagonalInches,
  calibration,
}: PanelBoardProps) {
  const t = useTranslations("boardDisplay");
  const wrapRef = useRef<HTMLDivElement>(null);
  const [grid, setGrid] = useState<GridRect | null>(null);
  const [scale, setScale] = useState(1);

  const messageLabel = useCallback((m: string) => t("withMessage", { message: m }), [t]);

  useLayoutEffect(() => {
    const wrapper = wrapRef.current;
    const board = wrapper?.querySelector<HTMLElement>("[data-board-preview]");
    if (!wrapper || !board) return;

    const measure = () => {
      const first = board.querySelector<HTMLElement>('[data-testid="char-tile-0-0"]');
      const last = board.querySelector<HTMLElement>(`[data-testid="char-tile-${rows - 1}-${cols - 1}"]`);
      if (!first || !last) return;
      const firstPos = offsetWithin(first, wrapper);
      const lastPos = offsetWithin(last, wrapper);
      const rect: GridRect = {
        x: firstPos.x,
        y: firstPos.y,
        width: lastPos.x + last.offsetWidth - firstPos.x,
        height: lastPos.y + last.offsetHeight - firstPos.y,
      };
      if (rect.width <= 0 || rect.height <= 0) return;
      setGrid(rect);
      try {
        setScale(
          panelAutofitScale({
            screenWidthPx: window.screen.width,
            screenHeightPx: window.screen.height,
            diagonalInches,
            cols,
            gridWidthPx: rect.width,
            gridHeightPx: rect.height,
            calibration,
            colPitchIn: colPitchIn(deviceType),
          }),
        );
      } catch {
        // Unmeasurable screen (some TV browsers report 0) — show unscaled.
        setScale(1);
      }
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(board);
    return () => observer.disconnect();
  }, [diagonalInches, deviceType, calibration, rows, cols]);

  return (
    <Box data-testid="panel-board-scaler" style={{ transform: `scale(${scale})`, transformOrigin: "center center" }}>
      <Box
        data-testid="panel-board-crop"
        className="relative overflow-hidden"
        style={grid ? { width: grid.width, height: grid.height } : { opacity: 0 }}
      >
        <Box ref={wrapRef} className="absolute" style={grid ? { left: -grid.x, top: -grid.y } : undefined}>
          <BoardDisplay
            message={message}
            size="lg"
            boardType={boardColor}
            deviceType={deviceType}
            notesWide={notesWide}
            notesTall={notesTall}
            code62Glyph={code62Glyph}
            animationsEnabled
            flapSpeed="hardware"
            announceUpdates
            loadingLabel={t("loading")}
            emptyLabel={t("empty")}
            messageLabel={messageLabel}
          />
        </Box>
        {/* Plastic-flap sheen: one overlay above the whole grid, no
            package-internal selectors. */}
        <Box
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(115deg, transparent 32%, rgba(255,255,255,0.05) 46%, rgba(255,255,255,0.02) 52%, transparent 64%)",
            mixBlendMode: "screen",
          }}
        />
      </Box>
    </Box>
  );
}
