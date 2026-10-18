"use client";

import { type BoardCellGrid, Box, type DeviceModel, DisplayPreview, TvFrame } from "@fiestaboard/ui";

import { PanelMatrix } from "@/components/panel/panel-matrix";
import { usePanelFrame } from "@/hooks/use-panel";
import type { MatrixSizing } from "@/lib/api";
import { computeAutofitGrid } from "@/lib/panel-scale";

// Matches the server's FiestaPanel 5x7 face. Available before switching a
// split-flap panel to LED, when its public config still carries the old style.
const baseModel: DeviceModel = {
  id: "fiestapanel_led_matrix",
  label: "FiestaPanel (LED matrix)",
  technology: "led_matrix",
  family: "fiestapanel",
  geometry: { kind: "pixels", width: 192, height: 96 },
  color: { kind: "rgb", bitDepth: 24 },
  charset: "led_5x7",
  font: "5x7",
  animation: { delivery: "stream", maxFps: 60 },
  appearance: { pixelShape: "square", dotRatio: 0.82, offColor: "#1a1a1a", substrateColor: "#000000" },
};

/** Unsaved settings preview the same live frame with the proposed TV and pixel geometry. */
export function PanelMatrixEditorPreview({
  panelId,
  diagonal,
  aspectW,
  aspectH,
  sizing,
  spacing,
  calibration,
}: {
  panelId: string;
  diagonal: number;
  aspectW: number;
  aspectH: number;
  sizing: MatrixSizing | null;
  spacing: number;
  calibration: number;
}) {
  const frame = usePanelFrame(panelId);
  const { rows, cols } = computeAutofitGrid(diagonal, aspectW, aspectH);
  const model: DeviceModel = {
    ...baseModel,
    geometry: {
      kind: "pixels",
      width: Math.max(192, cols * 6),
      height: Math.max(96, rows * 8),
    },
  };
  if (sizing === null) {
    return (
      <Box style={{ maxWidth: 260 }}>
        <DisplayPreview
          model={model}
          message={frame.data?.message ?? null}
          cells={frame.data?.cells as BoardCellGrid | undefined}
          frame="tv"
          tv={{ diagonalInches: diagonal, aspect: { w: aspectW, h: aspectH } }}
        />
      </Box>
    );
  }
  return (
    <Box style={{ maxWidth: 260 }}>
      <TvFrame className="panel-matrix-tv" diagonalInches={diagonal} aspect={{ w: aspectW, h: aspectH }}>
        <PanelMatrix
          model={model}
          message={frame.data?.message ?? null}
          cells={frame.data?.cells as BoardCellGrid | undefined}
          sizing={sizing}
          diagonal={diagonal}
          spacing={Number.isFinite(spacing) && spacing >= 1 && spacing <= 20 ? spacing : 6}
          calibration={Number.isFinite(calibration) && calibration >= 0.85 && calibration <= 1.15 ? calibration : 1}
        />
      </TvFrame>
    </Box>
  );
}
