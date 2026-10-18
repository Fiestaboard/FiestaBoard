"use client";

import { type BoardCellGrid, Box, type DeviceModel, LedMatrixDisplay } from "@fiestaboard/ui";
import { useCallback, useId, useLayoutEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { MatrixSizing } from "@/lib/api";
import { ledLetterCase } from "@/lib/device-preview";
import { panelMatrixLayout } from "@/lib/panel-matrix-layout";

/** Shared matrix presentation for the browser viewer and the panel editor's TV preview. */
export function PanelMatrix({
  model,
  message,
  cells,
  sizing,
  diagonal,
  spacing = 6,
  calibration = 1,
  physicalScreen = false,
}: {
  model: DeviceModel;
  message: string | null;
  cells?: BoardCellGrid;
  sizing: MatrixSizing;
  diagonal: number;
  spacing?: number;
  calibration?: number;
  /** Real viewer uses the entire monitor for pixel density, even when windowed. */
  physicalScreen?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const pattern = useId();
  const [size, setSize] = useState({ width: 0, height: 0 });
  const t = useTranslations("boardDisplay");
  const messageLabel = useCallback((m: string) => t("withMessage", { message: m }), [t]);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setSize({ width: element.clientWidth, height: element.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const geometry = model.geometry;
  if (geometry.kind !== "pixels") return null;
  const { width, height } = geometry;
  const layout =
    size.width > 0 && size.height > 0
      ? panelMatrixLayout(width, height, size.width, size.height, sizing, diagonal, spacing, {
          calibration,
          ...(physicalScreen && window.screen.width > 0 && window.screen.height > 0
            ? { screenWidth: window.screen.width, screenHeight: window.screen.height }
            : {}),
        })
      : { pitch: 1, x: 0, y: 0 };
  const look = model.appearance;
  const ratio = Math.max(0.1, Math.min(1, look?.dotRatio ?? 0.82));
  const dot = layout.pitch * ratio;
  const inset = (layout.pitch - dot) / 2;
  return (
    <Box
      ref={ref}
      data-testid="panel-matrix"
      data-sizing={sizing}
      style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: "black" }}
    >
      {sizing === "fill_tv" && (
        <svg
          aria-hidden="true"
          width="100%"
          height="100%"
          style={{ position: "absolute", inset: 0, background: look?.substrateColor ?? "#000000" }}
        >
          <defs>
            <pattern
              id={pattern}
              patternUnits="userSpaceOnUse"
              x={layout.x}
              y={layout.y}
              width={layout.pitch}
              height={layout.pitch}
            >
              {look?.pixelShape === "round" ? (
                <circle cx={layout.pitch / 2} cy={layout.pitch / 2} r={dot / 2} fill={look?.offColor ?? "#1a1a1a"} />
              ) : (
                <rect x={inset} y={inset} width={dot} height={dot} fill={look?.offColor ?? "#1a1a1a"} />
              )}
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill={`url(#${pattern})`} />
        </svg>
      )}
      <Box
        style={{
          position: "absolute",
          left: layout.x,
          top: layout.y,
          width: width * 9,
          height: height * 9,
          transform: `scale(${layout.pitch / 9})`,
          transformOrigin: "top left",
        }}
      >
        <LedMatrixDisplay
          model={model}
          message={message}
          cells={cells}
          size="lg"
          bezel={false}
          letterCase={ledLetterCase(model)}
          announceUpdates
          messageLabel={messageLabel}
          emptyLabel={t("empty")}
        />
      </Box>
    </Box>
  );
}
