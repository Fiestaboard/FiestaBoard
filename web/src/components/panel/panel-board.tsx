"use client";

import { BoardDisplay, type Code62Glyph, type DeviceType } from "@fiestaboard/ui";
import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { panelBoardScale } from "@/lib/panel-scale";

interface PanelBoardProps {
  message: string | null;
  deviceType: "flagship" | "note";
  boardColor: "black" | "white";
  code62Glyph: Code62Glyph;
  diagonalInches: number;
  calibration: number;
}

/**
 * Renders the package board at true physical size.
 *
 * The board is rendered at `size="lg"`, its unscaled bezel width is
 * measured, and a CSS transform brings it to the real unit's width
 * (Flagship 41.2″, Note 24.5″) for the screen the user described.
 *
 * Deliberately NOT `ScaledBoardDisplay` — that clamps to scale ≤ 1 to fit
 * containers, while life-size on a big TV regularly needs scale > 1.
 *
 * Also deliberately not the app's `BoardDisplay` wrapper: the wrapper wires
 * in the signed-in user's animation settings, which a TV with no session
 * can't read. The panel always animates (the package still honors
 * `prefers-reduced-motion` internally) at the `hardware` cadence.
 */
export function PanelBoard({
  message,
  deviceType,
  boardColor,
  code62Glyph,
  diagonalInches,
  calibration,
}: PanelBoardProps) {
  const t = useTranslations("boardDisplay");
  const wrapRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  const messageLabel = useCallback((m: string) => t("withMessage", { message: m }), [t]);

  useLayoutEffect(() => {
    const board = wrapRef.current?.querySelector<HTMLElement>("[data-board-preview]");
    if (!board) return;

    const measure = () => {
      const naturalWidth = board.offsetWidth;
      if (naturalWidth <= 0) return;
      try {
        setScale(
          panelBoardScale({
            screenWidthPx: window.screen.width,
            screenHeightPx: window.screen.height,
            diagonalInches,
            deviceType,
            boardNaturalWidthPx: naturalWidth,
            calibration,
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
  }, [diagonalInches, deviceType, calibration]);

  return (
    <div
      ref={wrapRef}
      data-testid="panel-board-scaler"
      style={{ transform: `scale(${scale})`, transformOrigin: "center center" }}
    >
      <div
        className="relative"
        style={{ filter: "drop-shadow(0 24px 48px rgba(0,0,0,0.55)) drop-shadow(0 4px 12px rgba(0,0,0,0.4))" }}
      >
        <BoardDisplay
          message={message}
          size="lg"
          boardType={boardColor}
          deviceType={deviceType as DeviceType}
          code62Glyph={code62Glyph}
          animationsEnabled
          flapSpeed="hardware"
          announceUpdates
          loadingLabel={t("loading")}
          emptyLabel={t("empty")}
          messageLabel={messageLabel}
        />
        {/* Plastic-flap sheen: one overlay above the whole board, no
            package-internal selectors. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(115deg, transparent 32%, rgba(255,255,255,0.05) 46%, rgba(255,255,255,0.02) 52%, transparent 64%)",
            mixBlendMode: "screen",
          }}
        />
      </div>
    </div>
  );
}
