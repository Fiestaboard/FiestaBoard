"use client";

import { type BoardCellGrid, Box, DisplayPreview, Text, TvFrame } from "@fiestaboard/ui";

import { PanelMatrix } from "@/components/panel/panel-matrix";
import { usePanelFrame } from "@/hooks/use-panel";
import { useTranslations } from "@/i18n/translations";
import type { MatrixSizing, PanelGeometry } from "@/lib/api";
import { ledLayerProps } from "@/lib/device-preview";
import { compatiblePanelFrame } from "@/lib/panel-frame";

/** Preview the server-resolved draft surface, with content only from a matching frame. */
export function PanelMatrixEditorPreview({
  geometry,
  panelId,
  diagonal,
  aspectW,
  aspectH,
  sizing,
  spacing,
  calibration,
}: {
  geometry: PanelGeometry;
  panelId: string;
  diagonal: number;
  aspectW: number;
  aspectH: number;
  sizing: MatrixSizing | null;
  spacing: number;
  calibration: number;
}) {
  const frame = usePanelFrame(panelId);
  const t = useTranslations("fiestaPanels");
  const model = geometry.device_model_spec;
  // A draft needs a shared identity even when the dimensions happen to match.
  const compatibleFrame =
    frame.data?.geometry_key && geometry.geometry_key ? compatiblePanelFrame(geometry, frame.data) : undefined;
  const pendingContent = !compatibleFrame && (
    <Text size="xs" tone="muted">
      {t("draftContentPending")}
    </Text>
  );
  if (sizing === null) {
    return (
      <Box style={{ maxWidth: 260 }}>
        <DisplayPreview
          model={model}
          message={compatibleFrame?.message ?? null}
          cells={compatibleFrame?.cells as BoardCellGrid | undefined}
          {...ledLayerProps(compatibleFrame?.layers)}
          frame="tv"
          tv={{ diagonalInches: diagonal, aspect: { w: aspectW, h: aspectH } }}
        />
        {pendingContent}
      </Box>
    );
  }
  return (
    <Box style={{ maxWidth: 260 }}>
      <TvFrame className="panel-matrix-tv" diagonalInches={diagonal} aspect={{ w: aspectW, h: aspectH }}>
        <PanelMatrix
          model={model}
          message={compatibleFrame?.message ?? null}
          cells={compatibleFrame?.cells as BoardCellGrid | undefined}
          layers={compatibleFrame?.layers}
          sizing={sizing}
          diagonal={diagonal}
          spacing={Number.isFinite(spacing) && spacing >= 1 && spacing <= 20 ? spacing : 6}
          calibration={Number.isFinite(calibration) && calibration >= 0.85 && calibration <= 1.15 ? calibration : 1}
        />
      </TvFrame>
      {pendingContent}
    </Box>
  );
}
