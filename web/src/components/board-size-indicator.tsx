import { Text } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import { isNoteArray, isPanel, NOTE_ARRAY_PRESETS, resolveDimensions } from "@/lib/board-dimensions";

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
  const { rows, cols } = resolveDimensions(deviceType, notesWide, notesTall, gridRows, gridCols);
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
      : null;

  // aria-label explicitly names each dimension (rows/columns), so screen-reader
  // users get an unambiguous reading regardless of the visual order below.
  const ariaLabel = presetLabel
    ? t("ariaLabelWithLayout", { rows, cols, layout: presetLabel })
    : t("ariaLabel", { rows, cols });

  return (
    <Text
      as="span"
      size="xs"
      tone="muted"
      role="img"
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-1 font-mono tabular-nums${className ? ` ${className}` : ""}`}
    >
      {/* Rows × cols (height × width) per the note-array epic convention; the
          wizard "characters" strings and tests use the same rows × cols order. */}
      {rows} × {cols}
      {presetLabel && (
        <>
          <Text as="span" size="xs" className="text-muted-foreground/50 mx-0.5">
            ·
          </Text>
          <Text as="span" size="xs" tone="muted">
            {presetLabel}
          </Text>
        </>
      )}
    </Text>
  );
}
