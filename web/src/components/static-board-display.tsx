"use client";

import {
  StaticBoardDisplay as UIStaticBoardDisplay,
  type StaticBoardDisplayProps as UIStaticBoardDisplayProps,
} from "@fiestaboard/ui";
import { memo } from "react";

import { useTranslations } from "@/i18n/translations";

/**
 * Zero-overhead static board for previews, from `@fiestaboard/ui`.
 *
 * No per-tile state, effects or refs — a pure grid of positioned elements,
 * which is what makes a wall of thumbnails (the page grid) affordable. This
 * file was a fork of the package's component; all that is left is the app's
 * translated accessible name.
 */
export type StaticBoardDisplayProps = Omit<UIStaticBoardDisplayProps, "previewLabel" | "messageLabel" | "emptyLabel">;

export const StaticBoardDisplay = memo(function StaticBoardDisplay(props: StaticBoardDisplayProps) {
  const t = useTranslations("boardDisplay");
  // `previewLabel` (a fixed name) rather than `messageLabel` (derived from the
  // board's own text), preserving what these previews have always announced.
  // The package's default would name each thumbnail by its content, which is
  // better, but it is a change to what a screen reader says on the page grid
  // and does not belong in a migration.
  return <UIStaticBoardDisplay {...props} previewLabel={t("preview")} emptyLabel={t("empty")} />;
});
