import { BoardSizeIndicator as UIBoardSizeIndicator, type DeviceType } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import { isNoteArray, isPanel, NOTE_ARRAY_PRESETS } from "@/lib/board-dimensions";

interface BoardSizeIndicatorProps {
  /** "flagship" | "note" | "note_array" | "panel" */
  deviceType: string;
  /** Notes wide (only used when deviceType === "note_array"; default 1) */
  notesWide?: number;
  /** Notes tall (only used when deviceType === "note_array"; default 1) */
  notesTall?: number;
  /** Rows of characters (only used when deviceType === "panel") */
  gridRows?: number | null;
  /** Columns of characters (only used when deviceType === "panel") */
  gridCols?: number | null;
  /** Optional extra className for the wrapping element */
  className?: string;
}

function resolvePresetId(notesWide: number, notesTall: number): string | null {
  const match = NOTE_ARRAY_PRESETS.find((p) => p.notes_wide === notesWide && p.notes_tall === notesTall);
  return match ? match.id : null;
}

/** Narrow the API's free-form device type; unknown types fall back to flagship, as resolveDimensions does. */
function toDeviceType(deviceType: string): DeviceType {
  return deviceType === "note" || deviceType === "note_array" || deviceType === "panel" ? deviceType : "flagship";
}

/**
 * The kit's size readout, wired to the app's note-array presets and
 * translations. The kit does not model named presets, so the localized layout
 * name is resolved here and passed in as `layoutLabel`.
 *
 * It reads `cols × rows` ("45 × 3"), the order 07 `57:27771` and 02 `36:35275`
 * print it in (slice 2.4), and is named "45 columns by 3 rows".
 */
export function BoardSizeIndicator({
  deviceType,
  notesWide = 1,
  notesTall = 1,
  gridRows,
  gridCols,
  className,
}: BoardSizeIndicatorProps) {
  const t = useTranslations("boardSizeIndicator");
  // Preset names are localized under the displaySettings namespace so the
  // indicator shows the SAME translated label as the Settings board-type
  // selector — not the raw English label baked into board-dimensions.ts (which
  // previously leaked into both the visible text and the aria-label).
  const tSettings = useTranslations("displaySettings");
  const noteArray = isNoteArray(deviceType);
  const panel = isPanel(deviceType);
  // Single fallback point: a matched preset's localized label, else "Custom".
  // A panel (FiestaPanel) is any rows × cols, so it is labelled as a panel.
  const presetId = noteArray ? resolvePresetId(notesWide, notesTall) : null;
  const presetLabel = noteArray
    ? presetId
      ? tSettings(`presets.${presetId}`)
      : t("custom")
    : panel
      ? t("panel")
      : undefined;

  return (
    <UIBoardSizeIndicator
      deviceType={toDeviceType(deviceType)}
      notesWide={notesWide}
      notesTall={notesTall}
      gridRows={gridRows ?? undefined}
      gridCols={gridCols ?? undefined}
      layoutLabel={presetLabel}
      format="cols×rows"
      labels={{
        dimensions: (rows, cols) => t("ariaLabelColsRows", { rows, cols }),
        dimensionsWithLayout: (rows, cols, layout) => t("ariaLabelColsRowsWithLayout", { rows, cols, layout }),
      }}
      className={className}
    />
  );
}
