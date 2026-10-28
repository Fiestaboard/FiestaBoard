import type { PanelFrame } from "@/lib/api";

/** Polls can straddle a geometry change: discard the entire old frame. */
export function compatiblePanelFrame(
  geometry: { rows?: number | null; cols?: number | null; geometry_key?: string },
  frame: PanelFrame | undefined,
): PanelFrame | undefined {
  if (!frame) return undefined;
  if (geometry.rows != null && geometry.rows !== frame.rows) return undefined;
  if (geometry.cols != null && geometry.cols !== frame.cols) return undefined;
  if (geometry.geometry_key && frame.geometry_key && geometry.geometry_key !== frame.geometry_key) return undefined;
  return frame;
}
