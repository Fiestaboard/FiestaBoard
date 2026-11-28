// The bridge between the page editor's formula IDE (web 2.10) and the TipTap
// formula chips. Without a provider (every other TipTap host) the chips
// behave exactly as before.

"use client";

import { createContext, useContext } from "react";

import type { RenderPreviewContext, RenderTarget } from "@/lib/api/formula-debug";
import type { AtomHint } from "@/lib/formula-ide/hints";

/** What a formula being edited renders against: the page's board and preview data. */
export interface FormulaPreviewTarget {
  /** The board the page renders for; the template is the edited formula alone. */
  target: Omit<RenderTarget, "template" | "lineMetadata">;
  /** Live (null), Sample, Missing or another time, as the preview shows. */
  context: RenderPreviewContext | null;
  /** Board width in tiles, for "4 of 22 columns". */
  boardCols: number;
}

export interface OpenFormulaRequest {
  /** The chip's expression body (no `{{= }}`); empty for a new formula. */
  expression: string;
  /** Writes the edited body back into the chip (one undoable transaction). */
  apply: (expression: string) => void;
  /** Called when the editor closes without applying. */
  cancel: () => void;
}

export interface FormulaIdeBridge {
  /** The H5 value hint for a chip's expression, if the last render saw it. */
  hint: (expression: string) => AtomHint | undefined;
  /**
   * Opens the page editor's formula editor: docked from 1024 px, a bottom
   * sheet from 640 to 1023 (W-5). Returns false on a phone or where the IDE
   * is unavailable, so the chip falls back to its own sheet or dialog.
   */
  openFormula: (request: OpenFormulaRequest) => boolean;
  /** Long-press / context menu › Inspect: steps and fit for one formula. */
  inspectFormula: (expression: string) => void;
  /**
   * The value a variable chip shows (`plugin.field`), read in the same preview
   * context as the formula hints (BB-FP-11). Undefined until rendered.
   */
  variableHint?: (path: string) => AtomHint | undefined;
  /** The board and preview data a formula sheet evaluates against (BB-FP-14). */
  preview?: FormulaPreviewTarget | null;
  /**
   * The 1-based template line the docked editor or Inspect is about; the
   * template tints it (Figma 111:30911, 132:20145; BB-FP-15/16).
   */
  activeLine?: number | null;
}

export const FormulaIdeContext = createContext<FormulaIdeBridge | null>(null);

export function useFormulaIdeBridge(): FormulaIdeBridge | null {
  return useContext(FormulaIdeContext);
}
