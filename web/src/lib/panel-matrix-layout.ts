import type { MatrixSizing } from "@/lib/api";

/** Uniform LED pitch: presentation never changes the source pixel or character grid. */
export function panelMatrixLayout(
  columns: number,
  rows: number,
  width: number,
  height: number,
  sizing: MatrixSizing,
  diagonal: number,
  spacing: number,
  {
    calibration = 1,
    screenWidth = width,
    screenHeight = height,
  }: {
    calibration?: number;
    screenWidth?: number;
    screenHeight?: number;
  } = {},
) {
  const fit = Math.min(width / columns, height / rows);
  const pixelsPerMm = Math.hypot(screenWidth, screenHeight) / (diagonal * 25.4);
  const pitch = sizing === "true_size" ? Math.min(fit, pixelsPerMm * spacing * calibration) : fit;
  return { pitch, x: (width - columns * pitch) / 2, y: (height - rows * pitch) / 2 };
}
