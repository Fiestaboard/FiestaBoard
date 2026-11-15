"use client";

import { ScaledBoardDisplay as UIScaledBoardDisplay } from "@fiestaboard/ui";
import { memo } from "react";

import { useBoardChrome } from "@/components/board-display";
import { BoardViewport, type BoardViewportProps } from "@/components/board-viewport";
import { useTranslations } from "@/i18n/translations";

/**
 * The board almost every surface renders. Since web 2.4 (WEB-07) it is a
 * {@link BoardViewport}: a board that does not fit keeps its real tiles and
 * scrolls inside its bezel, and Actual size is the default for every board type
 * (owner rule 9: boards never shrink, they scroll). Fit is the opt-in overview.
 *
 * The name stays so every caller converts at once, including surfaces other
 * slices are rebuilding (Home, the editor, Compose). New code should import
 * `BoardViewport` directly.
 *
 * `thumbnail` keeps the old fit-to-slot picture for the two places a scroll
 * region cannot live: the board inside a page card's `<button>` (a focusable
 * region or a toggle there is a nested interactive control), and the inert,
 * decorative collection stack. A thumbnail is always `fit`, draws no Fit /
 * Actual pills, never reads or writes the session's mode, and so never turns
 * into a scroller or a control.
 */
export type ScaledBoardDisplayProps = BoardViewportProps & {
  /** A fit-scaled picture for a card or decorative stack, not a viewport. */
  thumbnail?: boolean;
};

const ThumbnailBoard = memo(function ThumbnailBoard({
  flapSpeed,
  // Viewport-only props have no meaning on a thumbnail.
  regionLabel: _regionLabel,
  title: _title,
  minTile: _minTile,
  indicator: _indicator,
  rootClassName: _rootClassName,
  mode: _mode,
  onModeChange: _onModeChange,
  defaultMode: _defaultMode,
  persist: _persist,
  showModeToggle: _showModeToggle,
  ...props
}: BoardViewportProps) {
  const t = useTranslations("boardDisplay");
  const chrome = useBoardChrome(flapSpeed);
  return (
    <UIScaledBoardDisplay
      {...props}
      {...chrome}
      mode="fit"
      persist={false}
      // A picture has no controls: no Fit / Actual pills inside a page card's
      // button (axe nested-interactive), FiestaUI 1.5d.
      showModeToggle={false}
      previewSizeLabel={t("previewSizeLabel")}
      fitModeLabel={t("fitMode")}
      actualModeLabel={t("actualMode")}
    />
  );
});

export const ScaledBoardDisplay = memo(function ScaledBoardDisplay({ thumbnail, ...props }: ScaledBoardDisplayProps) {
  return thumbnail ? <ThumbnailBoard {...props} /> : <BoardViewport {...props} />;
});
