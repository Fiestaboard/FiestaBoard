"use client";

import { ScaledBoardDisplay as UIScaledBoardDisplay } from "@fiestaboard/ui";
import { memo } from "react";

import { type BoardDisplayProps, useBoardChrome } from "@/components/board-display";
import { useTranslations } from "@/i18n/translations";

/**
 * {@link BoardDisplay} wrapped so it shrinks to fit a narrow parent, from
 * `@fiestaboard/ui`.
 *
 * This is the wrapper almost every surface should render: the board sizes its
 * tiles from viewport breakpoints, so an unscaled 6x22 flagship overflows a
 * phone's content box and any pane narrowed by a sibling (issue #1397,
 * FiestaUI #192). Note arrays additionally get a Fit / Actual size toggle.
 *
 * The measuring, the toggle and its `sessionStorage` persistence all live in
 * the package now — including the same `fiestaboard:boardPreviewMode` key and
 * `data-testid="actual-size-scroll"` hook the app's fork used.
 */
export type ScaledBoardDisplayProps = BoardDisplayProps;

export const ScaledBoardDisplay = memo(function ScaledBoardDisplay({ flapSpeed, ...props }: ScaledBoardDisplayProps) {
  const t = useTranslations("boardDisplay");
  const chrome = useBoardChrome(flapSpeed);

  return (
    <UIScaledBoardDisplay
      {...props}
      {...chrome}
      previewSizeLabel={t("previewSizeLabel")}
      fitModeLabel={t("fitMode")}
      actualModeLabel={t("actualMode")}
    />
  );
});
