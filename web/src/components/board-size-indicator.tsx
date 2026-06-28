import { useTranslations } from "@/i18n/translations";
import { isNoteArray, NOTE_ARRAY_PRESETS, resolveDimensions } from "@/lib/board-dimensions";

interface BoardSizeIndicatorProps {
  /** "flagship" | "note" | "note_array" */
  deviceType: string;
  /** Notes wide (only used when deviceType === "note_array"; default 1) */
  notesWide?: number;
  /** Notes tall (only used when deviceType === "note_array"; default 1) */
  notesTall?: number;
  /** Optional extra className for the wrapping element */
  className?: string;
}

function resolvePresetId(notesWide: number, notesTall: number): string | null {
  const match = NOTE_ARRAY_PRESETS.find((p) => p.notes_wide === notesWide && p.notes_tall === notesTall);
  return match ? match.id : null;
}

export function BoardSizeIndicator({ deviceType, notesWide = 1, notesTall = 1, className }: BoardSizeIndicatorProps) {
  const t = useTranslations("boardSizeIndicator");
  // Preset names are localized under the displaySettings namespace so the
  // indicator shows the SAME translated label as the Settings board-type
  // selector — not the raw English label baked into board-dimensions.ts (which
  // previously leaked into both the visible text and the aria-label).
  const tSettings = useTranslations("displaySettings");
  const { rows, cols } = resolveDimensions(deviceType, notesWide, notesTall);
  const noteArray = isNoteArray(deviceType);
  // Single fallback point: a matched preset's localized label, else "Custom".
  const presetId = noteArray ? resolvePresetId(notesWide, notesTall) : null;
  const presetLabel = noteArray ? (presetId ? tSettings(`presets.${presetId}`) : t("custom")) : null;

  // aria-label explicitly names each dimension (rows/columns), so screen-reader
  // users get an unambiguous reading regardless of the visual order below.
  const ariaLabel = noteArray
    ? t("ariaLabelWithLayout", { rows, cols, layout: presetLabel })
    : t("ariaLabel", { rows, cols });

  return (
    <span
      role="img"
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-1 text-xs text-muted-foreground font-mono tabular-nums${className ? ` ${className}` : ""}`}
    >
      {/* Rows × cols (height × width) per the note-array epic convention; the
          wizard "characters" strings and tests use the same rows × cols order. */}
      {rows} × {cols}
      {noteArray && (
        <>
          <span className="text-muted-foreground/50 mx-0.5">·</span>
          <span>{presetLabel}</span>
        </>
      )}
    </span>
  );
}
