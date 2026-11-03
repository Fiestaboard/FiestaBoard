"use client";

import { type BoardCellGrid, type DeviceModel, DisplayPreview } from "@fiestaboard/ui";
import { memo, type ReactNode, useCallback } from "react";

import { useTranslations } from "@/i18n/translations";
import type { BoardLedLayout, CanvasLayerJson } from "@/lib/api";
import {
  isLedModel,
  ledLayerProps,
  ledLayoutProps,
  ledLetterCase,
  physicalFramePreviewModel,
} from "@/lib/device-preview";

export interface DevicePreviewProps {
  /** The board's device model (`resolveBoardModel`); `null` when unknown. */
  model: DeviceModel | null;
  /** Board markup. Ignored when `cells` is given. */
  message?: string | null;
  /** Parsed cells (`BoardToken[][]`) where the API provides them; win over `message`. */
  cells?: BoardCellGrid;
  /** A pixel board's canvas layers (`layers` from the API), drawn over the cells. Ignored for a split-flap board. */
  layers?: CanvasLayerJson[] | null;
  size?: "sm" | "md" | "lg";
  /** A fixed accessible name (thumbnails), instead of one built from the message. */
  previewLabel?: string;
  /**
   * The board's LED layout choices (`led_layout`): tile gaps filled, block
   * padding. They change what the device is sent, so the preview draws them
   * too. Ignored for a split-flap board.
   */
  ledLayout?: BoardLedLayout | null;
  /**
   * The split-flap board this surface has always drawn — its own wrapper, so
   * the user's animation and flap-speed settings, the Fit / Actual toggle and
   * draw mode's tile hit-testing stay exactly as they were.
   */
  children: ReactNode;
}

/**
 * One preview entry point for a board of any technology.
 *
 * A board whose model is an LED matrix is drawn by FiestaUI's
 * `DisplayPreview` (which dispatches it to `LedMatrixDisplay`): a split-flap
 * renderer cannot draw pixels. Every other board — split-flap, or a model
 * the app cannot resolve — renders `children`, the surface's existing
 * split-flap board, untouched: `DisplayPreview` has no slot for the app's
 * animation gate, flap cadence or fit toggle, and a split-flap board must
 * look exactly as it did.
 */
export const DevicePreview = memo(function DevicePreview({
  model,
  message,
  cells,
  layers,
  size,
  previewLabel,
  ledLayout,
  children,
}: DevicePreviewProps) {
  const t = useTranslations("boardDisplay");
  const messageLabel = useCallback((m: string) => t("withMessage", { message: m }), [t]);
  if (!isLedModel(model)) return <>{children}</>;
  const physical =
    layers?.length === 1 &&
    layers[0].physical_frame_version === 1 &&
    layers[0].x === 0 &&
    layers[0].y === 0 &&
    [layers[0].width, layers[0].height].every((n) => Number.isInteger(n) && n >= 1 && n <= 512)
      ? layers[0]
      : undefined;
  const previewModel = physicalFramePreviewModel(model, physical)!;

  return (
    <DisplayPreview
      {...ledLayoutProps(ledLayout)}
      {...ledLayerProps(layers)}
      model={previewModel}
      message={message ?? null}
      cells={cells}
      size={size}
      letterCase={ledLetterCase(model)}
      previewLabel={previewLabel}
      messageLabel={messageLabel}
      emptyLabel={t("empty")}
    />
  );
});
