import type { CanvasContent } from "./canvas";

/** Unknown document fields are retained whenever an editor replaces a subtree. */
export interface FlexibleStyle {
  [key: string]: unknown;
  font?: string | null;
  size?: string | number | null;
  color?: string | null;
  background?: string | null;
  align?: string | null;
  case?: string | null;
  overflow?: string | null;
  height?: string | number | null;
}

export interface FlexibleBlock {
  [key: string]: unknown;
  id: string;
  kind: string;
  text?: string | null;
  canvas?: { [key: string]: unknown; content?: CanvasContent | null; source?: string | null } | null;
  style?: FlexibleStyle | null;
  priority?: number | null;
  if?: string | null;
}

export interface FlexibleFields {
  blocks?: FlexibleBlock[] | null;
  style?: FlexibleStyle | null;
  layout?: { [key: string]: unknown; kind?: string; valign?: string; gap?: string | number } | null;
  targets?: { [key: string]: unknown; boards?: string[] | null; technology?: string[] | null } | null;
}

export interface LayoutIssue {
  path: string[];
  code: string;
  severity: "info" | "warning";
  message: string;
}
