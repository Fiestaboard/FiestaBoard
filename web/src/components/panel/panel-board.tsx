"use client";

import {
  type BoardCellGrid,
  BoardDisplay,
  Box,
  type Code62Glyph,
  type DeviceModel,
  type DeviceType,
  DisplayPreview,
} from "@fiestaboard/ui";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { isLedModel, ledLetterCase } from "@/lib/device-preview";
import { NOTE_COL_PITCH_IN, PANEL_PHYSICAL_WIDTH_IN, panelAutofitScale } from "@/lib/panel-scale";

interface PanelBoardProps {
  message: string | null;
  /** The frame as rich cells, when the frame has them; they win over `message`. */
  cells?: BoardCellGrid;
  /** The panel's render-style model (`device_model_spec`); an LED model draws as an LED matrix. */
  model?: DeviceModel | null;
  animationsEnabled: boolean;
  deviceType: DeviceType;
  notesWide: number;
  notesTall: number;
  /** Character grid of a "panel" board (ignored for every other type). */
  gridRows?: number;
  gridCols?: number;
  rows: number;
  cols: number;
  boardColor: "black" | "white";
  code62Glyph: Code62Glyph;
  diagonalInches: number;
  calibration: number;
}

/** How long to keep the board hidden while waiting for a first measurement. */
const MEASURE_GRACE_MS = 1500;

/** The LED board's margin to the screen edge, as a fraction of the shorter side (TvFrame's). */
const LED_SCREEN_MARGIN = 0.04;

/** Physical column pitch in inches for the board's device family. */
function colPitchIn(deviceType: DeviceType): number {
  // Auto-fit grids (per-character panels, and legacy Note-block arrays) use
  // the Note's column pitch; a legacy flagship panel anchors to the
  // Flagship's 41.2" / 22 columns instead.
  if (deviceType === "flagship") return PANEL_PHYSICAL_WIDTH_IN.flagship / 22;
  return NOTE_COL_PITCH_IN;
}

/**
 * The board as the TV shows it, filling the screen.
 *
 * Split-flap: only the flaps (`bezel={false}` — no housing, as the Apple TV
 * app draws FiestaPanel), so the board element *is* the tile grid and is
 * measured directly; scaled so each flap lands at real-world size, with a
 * gentle ≤10% stretch toward the nearest screen edge (panelAutofitScale).
 * This replaces rendering the housed board and cropping it to its tiles
 * through an overflow window positioned from measured tile offsets.
 *
 * LED matrix: the panel's LED model through `DisplayPreview`, scaled to fit
 * the screen — an LED face has no physical size to be true to.
 *
 * Measurement uses offset* geometry, which ignores CSS transforms, so the
 * scale never feeds back into itself.
 */
export function PanelBoard({
  message,
  cells,
  model,
  animationsEnabled,
  deviceType,
  notesWide,
  notesTall,
  gridRows,
  gridCols,
  rows,
  cols,
  boardColor,
  code62Glyph,
  diagonalInches,
  calibration,
}: PanelBoardProps) {
  const t = useTranslations("boardDisplay");
  const wrapRef = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState(false);
  const [scale, setScale] = useState(1);
  // Safety valve: the pre-measurement state hides the board (opacity 0 avoids
  // a flash of unscaled content). If measurement never succeeds — a TV
  // browser that lays the board out at zero size — the TV must NOT stay pure
  // black forever; after a grace period the board shows unscaled instead.
  const [measureTimedOut, setMeasureTimedOut] = useState(false);
  const led = isLedModel(model);

  const messageLabel = useCallback((m: string) => t("withMessage", { message: m }), [t]);

  useLayoutEffect(() => {
    const wrapper = wrapRef.current;
    const board = led ? wrapper?.firstElementChild : wrapper?.querySelector<HTMLElement>("[data-board-preview]");
    if (!wrapper || !(board instanceof HTMLElement)) return;

    const measure = () => {
      const width = board.offsetWidth;
      const height = board.offsetHeight;
      if (width <= 0 || height <= 0) return;
      setMeasured(true);
      try {
        if (led) {
          const screenW = window.innerWidth;
          const screenH = window.innerHeight;
          const inset = LED_SCREEN_MARGIN * Math.min(screenW, screenH);
          const fit = Math.min((screenW - 2 * inset) / width, (screenH - 2 * inset) / height);
          setScale(Number.isFinite(fit) && fit > 0 ? fit : 1);
          return;
        }
        setScale(
          panelAutofitScale({
            screenWidthPx: window.screen.width,
            screenHeightPx: window.screen.height,
            diagonalInches,
            cols,
            gridWidthPx: width,
            gridHeightPx: height,
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
  }, [led, diagonalInches, deviceType, calibration, rows, cols]);

  useEffect(() => {
    if (measured) return;
    const timer = setTimeout(() => setMeasureTimedOut(true), MEASURE_GRACE_MS);
    return () => clearTimeout(timer);
  }, [measured]);

  return (
    <Box
      data-testid="panel-board-scaler"
      data-animations={animationsEnabled ? "true" : "false"}
      style={{ transform: `scale(${scale})`, transformOrigin: "center center" }}
    >
      <Box
        ref={wrapRef}
        data-testid="panel-board-fit"
        className="panel-seamless"
        style={measured || measureTimedOut ? undefined : { opacity: 0 }}
      >
        {led ? (
          <DisplayPreview
            model={model}
            message={message}
            cells={cells}
            size="lg"
            letterCase={ledLetterCase(model)}
            announceUpdates
            messageLabel={messageLabel}
            emptyLabel={t("empty")}
          />
        ) : (
          <BoardDisplay
            message={message}
            cells={cells}
            bezel={false}
            size="lg"
            boardType={boardColor}
            deviceType={deviceType}
            notesWide={notesWide}
            notesTall={notesTall}
            gridRows={gridRows}
            gridCols={gridCols}
            code62Glyph={code62Glyph}
            animationsEnabled={animationsEnabled}
            flapSpeed="hardware"
            announceUpdates
            loadingLabel={t("loading")}
            emptyLabel={t("empty")}
            messageLabel={messageLabel}
          />
        )}
      </Box>
    </Box>
  );
}
