"use client";

import { Box, Stack, Text, TvFrame } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import { computeAutofitGrid, NOTE_COL_PITCH_IN, NOTE_ROW_PITCH_IN, screenDimensionsIn } from "@/lib/panel-scale";

interface TvPreviewProps {
  diagonalInches: number;
  aspectW: number;
  aspectH: number;
}

/** The screen's drawn width before `TvFrame` fits it; only its aspect matters. */
const SCREEN_PX = 480;

/**
 * True-to-shape preview of a FiestaPanel on its TV: FiestaUI's `TvFrame`
 * at the chosen size and aspect ratio, with the auto-fit character grid on
 * its screen at its real proportional coverage — so picking a size/aspect
 * immediately shows how many flaps you get and how much of the screen they
 * fill.
 *
 * The grid can be up to 128 × 96 flaps, so it is drawn as one element with a
 * repeating tile pattern rather than one node per flap (the live board, on
 * the panel's card, is `PanelTvPreview`).
 */
export function TvPreview({ diagonalInches, aspectW, aspectH }: TvPreviewProps) {
  const t = useTranslations("fiestaPanels");
  if (!(diagonalInches > 0) || !(aspectW > 0) || !(aspectH > 0)) return null;

  const [screenWidthIn, screenHeightIn] = screenDimensionsIn(diagonalInches, aspectW, aspectH);
  const { rows, cols } = computeAutofitGrid(diagonalInches, aspectW, aspectH);
  // A pocket screen smaller than the minimum (Note-sized) grid still gets
  // that grid — the viewer shrinks it to fit, so cap the drawn coverage at
  // the full screen.
  const coverageW = Math.min(100, ((cols * NOTE_COL_PITCH_IN) / screenWidthIn) * 100);
  const coverageH = Math.min(100, ((rows * NOTE_ROW_PITCH_IN) / screenHeightIn) * 100);

  return (
    <Stack gap="1" data-testid="tv-preview" style={{ maxWidth: 260 }}>
      <TvFrame diagonalInches={diagonalInches} aspect={{ w: aspectW, h: aspectH }}>
        {/* The whole screen at its aspect, for TvFrame to fit; the grid sits
            on it at the share of the screen it really covers. */}
        <Box
          className="flex items-center justify-center"
          style={{ width: SCREEN_PX, height: (SCREEN_PX * aspectH) / aspectW }}
        >
          <Box
            data-testid="tv-preview-grid"
            data-rows={rows}
            data-cols={cols}
            className="bg-neutral-700"
            style={{
              width: `${coverageW}%`,
              height: `${coverageH}%`,
              // One tile per flap: a black gutter on the right and bottom edge
              // of each cell, repeated cols × rows times.
              backgroundImage:
                "linear-gradient(to right, transparent 80%, #000 80%), linear-gradient(to bottom, transparent 80%, #000 80%)",
              backgroundSize: `${100 / cols}% ${100 / rows}%`,
            }}
          />
        </Box>
      </TvFrame>
      <Text size="xs" tone="muted" data-testid="tv-preview-meta">
        {t("tvPreviewMeta", { cols, rows })}
      </Text>
    </Stack>
  );
}
