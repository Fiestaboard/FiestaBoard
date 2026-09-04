"use client";

import { Box, Stack, Text } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import { NOTE_COLS, NOTE_ROWS } from "@/lib/board-dimensions";
import { BLOCK_HEIGHT_IN, BLOCK_WIDTH_IN, computeAutofitGrid, screenDimensionsIn } from "@/lib/panel-scale";

interface TvPreviewProps {
  diagonalInches: number;
  aspectW: number;
  aspectH: number;
}

/**
 * True-to-shape preview of a FiestaPanel on its TV: the screen outline at
 * the chosen aspect ratio with the auto-fit Note-block grid inside it at
 * its real proportional coverage — so picking a size/aspect immediately
 * shows how many flaps you get and how much of the screen they fill.
 *
 * App-side composite for now (it reads app i18n); a presentational
 * `TvPreview` in @fiestaboard/ui next to BoardDisplay is the eventual home.
 */
export function TvPreview({ diagonalInches, aspectW, aspectH }: TvPreviewProps) {
  const t = useTranslations("fiestaPanels");
  if (!(diagonalInches > 0) || !(aspectW > 0) || !(aspectH > 0)) return null;

  const [screenWidthIn, screenHeightIn] = screenDimensionsIn(diagonalInches, aspectW, aspectH);
  const { notesWide, notesTall } = computeAutofitGrid(diagonalInches, aspectW, aspectH);
  // A pocket screen smaller than one block still gets a 1×1 grid — the
  // viewer shrinks it to fit, so cap the drawn coverage at the full screen.
  const coverageW = Math.min(100, ((notesWide * BLOCK_WIDTH_IN) / screenWidthIn) * 100);
  const coverageH = Math.min(100, ((notesTall * BLOCK_HEIGHT_IN) / screenHeightIn) * 100);

  return (
    <Stack gap="1" data-testid="tv-preview">
      <Box
        className="w-full rounded-md border-4 border-neutral-700 bg-black"
        style={{ aspectRatio: `${aspectW} / ${aspectH}`, maxWidth: 260 }}
      >
        <Box className="flex h-full w-full items-center justify-center">
          <Box
            className="grid gap-[2px]"
            style={{
              width: `${coverageW}%`,
              height: `${coverageH}%`,
              gridTemplateColumns: `repeat(${notesWide}, 1fr)`,
              gridTemplateRows: `repeat(${notesTall}, 1fr)`,
            }}
          >
            {Array.from({ length: notesWide * notesTall }, (_, i) => (
              <Box
                key={i}
                data-testid="tv-preview-block"
                className="rounded-[2px] border border-neutral-600 bg-neutral-900"
              />
            ))}
          </Box>
        </Box>
      </Box>
      <Text size="xs" tone="muted" data-testid="tv-preview-meta">
        {t("tvPreviewMeta", {
          cols: notesWide * NOTE_COLS,
          rows: notesTall * NOTE_ROWS,
          wide: notesWide,
          tall: notesTall,
        })}
      </Text>
    </Stack>
  );
}
