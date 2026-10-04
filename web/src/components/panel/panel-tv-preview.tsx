"use client";

import { type BoardCellGrid, type DeviceModel, DisplayPreview, type TvFrameOptions } from "@fiestaboard/ui";
import { useCallback, useEffect, useState } from "react";

import { usePanelConfig, usePanelFrame } from "@/hooks/use-panel";
import { useTranslations } from "@/i18n/translations";
import type { PanelPublicConfig } from "@/lib/api";
import { isLedModel, ledLetterCase, resolveBoardModel } from "@/lib/device-preview";
import { isInDimWindow, PANEL_DIM_LEVEL } from "@/lib/panel-dim";

export { PANEL_DIM_LEVEL };

/** How often the dim window is re-evaluated (the viewer's cadence). */
const DIM_TICK_MS = 30_000;

/**
 * The television `TvFrame` draws, from what FiestaBoard holds per panel and
 * what its viewer would be doing: `screen_diagonal_inches` → `diagonalInches`,
 * `screen_aspect_w` / `_h` → `aspect` (16:9 for a panel stored before the
 * aspect existed), the auto-dim window → `dimmed` at the viewer's overlay
 * level, a failed frame fetch → `offline`. `calibration_scale` is a
 * physical-size nudge for the real TV and never reaches the frame.
 */
export function panelTvOptions(
  config: Pick<PanelPublicConfig, "screen_diagonal_inches" | "screen_aspect_w" | "screen_aspect_h">,
  state: { dimActive: boolean; offline: boolean },
): TvFrameOptions {
  return {
    diagonalInches: config.screen_diagonal_inches,
    aspect: { w: config.screen_aspect_w ?? 16, h: config.screen_aspect_h ?? 9 },
    dimmed: state.dimActive ? PANEL_DIM_LEVEL : 0,
    offline: state.offline,
  };
}

function minutesSinceMidnight(): number {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

interface PanelTvPreviewProps {
  panelId: string;
  /** Poll cadence override (tests). */
  frameIntervalMs?: number;
}

/**
 * A panel's live preview: the board its TV is showing right now, on the TV.
 *
 * FiestaUI's `DisplayPreview frame="tv"` draws the television around the
 * panel's render-style model — a split-flap panel as bare flaps on the black
 * (the TV draws no housing), an LED one as its matrix — fitted to the screen.
 * It reads the same public config and frame the viewer polls, so what it
 * shows is what the TV shows, dimming and losing signal included.
 */
export function PanelTvPreview({ panelId, frameIntervalMs }: PanelTvPreviewProps) {
  const t = useTranslations("fiestaPanels");
  const tBoard = useTranslations("boardDisplay");
  const config = usePanelConfig(panelId);
  const frame = usePanelFrame(panelId, frameIntervalMs);
  const [minutesNow, setMinutesNow] = useState(minutesSinceMidnight);
  const messageLabel = useCallback((m: string) => tBoard("withMessage", { message: m }), [tBoard]);

  useEffect(() => {
    const interval = setInterval(() => setMinutesNow(minutesSinceMidnight()), DIM_TICK_MS);
    return () => clearInterval(interval);
  }, []);

  const data = config.data;
  if (!data || data.board_missing) return null;

  // A server that predates render_style sends no model: the split-flap
  // panel built into FiestaUI draws the same flaps.
  const model: DeviceModel | string = resolveBoardModel(data) ?? "vestaboard_panel";
  const autoDim = data.auto_dim;
  const dimActive = !!autoDim?.enabled && isInDimWindow(minutesNow, autoDim.start, autoDim.end);
  const offline = frame.isError;
  const led = typeof model !== "string" && isLedModel(model);

  return (
    <DisplayPreview
      model={model}
      frame="tv"
      tv={{ ...panelTvOptions(data, { dimActive, offline }), offlineLabel: t("offline") }}
      message={frame.data?.message ?? null}
      cells={frame.data?.cells as BoardCellGrid | undefined}
      gridRows={data.rows ?? undefined}
      gridCols={data.cols ?? undefined}
      // The board colour is a split-flap housing option; an LED model offers none.
      appearance={!led && data.board_color ? { board_color: data.board_color } : undefined}
      code62Glyph={data.code62_glyph ?? undefined}
      letterCase={led ? ledLetterCase(model) : undefined}
      size="sm"
      messageLabel={messageLabel}
      emptyLabel={tBoard("empty")}
    />
  );
}
