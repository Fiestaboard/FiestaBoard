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

function resolvePresetLabel(notesWide: number, notesTall: number, tCustom: string): string {
  const match = NOTE_ARRAY_PRESETS.find((p) => p.notes_wide === notesWide && p.notes_tall === notesTall);
  return match ? match.label : tCustom;
}

export function BoardSizeIndicator({ deviceType, notesWide = 1, notesTall = 1, className }: BoardSizeIndicatorProps) {
  const t = useTranslations("boardSizeIndicator");
  const { rows, cols } = resolveDimensions(deviceType, notesWide, notesTall);
  const noteArray = isNoteArray(deviceType);
  const presetLabel = noteArray ? resolvePresetLabel(notesWide, notesTall, t("custom")) : null;

  const ariaLabel = noteArray
    ? t("ariaLabelWithLayout", { rows, cols, layout: presetLabel ?? t("custom") })
    : t("ariaLabel", { rows, cols });

  return (
    <span
      role="img"
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-1 text-xs text-muted-foreground font-mono tabular-nums${className ? ` ${className}` : ""}`}
    >
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
