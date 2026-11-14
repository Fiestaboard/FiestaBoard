"use client";

import {
  BoardViewport as UIBoardViewport,
  type BoardViewportLabels,
  type BoardViewportProps as UIBoardViewportProps,
  type DeviceType,
} from "@fiestaboard/ui";
import { memo, useMemo } from "react";

import { useBoardChrome } from "@/components/board-display";
import { useCoarsePointer } from "@/hooks/use-coarse-pointer";
import { useTranslations } from "@/i18n/translations";

/**
 * A board that keeps its real tiles and scrolls inside its bezel instead of
 * shrinking (owner rule 9, WEB-07), from `@fiestaboard/ui`.
 *
 * Figma: 07 `57:27771` (web editor, note array overflow), 02 `36:35275` and
 * `52:122709`–`52:123502` (every board type), 07c `310:68695`.
 *
 * The package does the work: the fixed bezel that clips, the 44 px edge fades,
 * snap per Note / Note column / tile column, the "Note 1 of 3" indicator, the
 * ← → Home End F keys, and the Fit view that is labelled an overview once its
 * tiles drop under the 13 px floor. Actual size is its default. What is left
 * here is the app's wiring: the same chrome as {@link BoardDisplay} (animation
 * gate, flap speed, translated names) and every string translated.
 *
 * The mode follows the kit's session key (`fiestaboard:boardPreviewMode`): a Fit
 * tap lasts the session and carries to boards mounted later.
 */
export type BoardViewportProps = Omit<
  UIBoardViewportProps,
  "animationsEnabled" | "loadingLabel" | "emptyLabel" | "messageLabel" | "labels" | "hint"
> & {
  /**
   * The scroll region's name. A list of boards names each one (for example
   * "Kitchen preview") so a screen reader can tell them apart; the default is
   * the translated "Board preview".
   */
  regionLabel?: string;
};

type Translate = (key: string, params?: Record<string, unknown>) => string;

/**
 * The hint appended after the indicator while a board scrolls.
 *
 * On a fine pointer it is 07's keyboard hint ("Shift + scroll, trackpad swipe,
 * or ← → when focused. Snaps to each Note."), ending in what the board snaps
 * to: a Note on a note array, a column on anything else. On a coarse pointer it
 * is 02's "swipe": a phone has no Shift key and no focus ring to speak of.
 */
export function boardViewportHint(t: Translate, deviceType: DeviceType | undefined, coarse: boolean): string {
  if (coarse) return t("viewportHintTouch");
  return t(deviceType === "note_array" ? "viewportHintNotes" : "viewportHintColumns");
}

/** Every BoardViewport string, translated. Stable while the language is. */
export function useBoardViewportLabels(regionLabel?: string): Required<BoardViewportLabels> {
  const t = useTranslations("boardDisplay");
  return useMemo(
    () => ({
      region: regionLabel ?? t("preview"),
      previewSize: t("previewSizeLabel"),
      fit: t("fitMode"),
      actual: t("actualMode"),
      note: (current: number, total: number) => t("viewportNote", { current, total }),
      arrayColumn: (current: number, total: number, notes: number) =>
        t("viewportArrayColumn", { current, total, notes }),
      columns: (first: number, last: number, total: number) => t("viewportColumns", { first, last, total }),
      overview: (notes: number | null, columns: number) =>
        notes === null ? t("viewportOverviewColumns", { columns }) : t("viewportOverviewNotes", { notes }),
    }),
    [t, regionLabel],
  );
}

export const BoardViewport = memo(function BoardViewport({ flapSpeed, regionLabel, ...props }: BoardViewportProps) {
  const t = useTranslations("boardDisplay");
  const chrome = useBoardChrome(flapSpeed);
  const labels = useBoardViewportLabels(regionLabel);
  const coarse = useCoarsePointer();
  return (
    <UIBoardViewport {...props} {...chrome} labels={labels} hint={boardViewportHint(t, props.deviceType, coarse)} />
  );
});
