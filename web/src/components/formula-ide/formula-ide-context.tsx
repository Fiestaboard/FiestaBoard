// The bridge between the page editor's formula IDE (web 2.10) and the TipTap
// formula chips. Without a provider (every other TipTap host) the chips
// behave exactly as before.

"use client";

import { createContext, useContext } from "react";

import type { AtomHint } from "@/lib/formula-ide/hints";

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
   * Opens the docked formula editor (desktop, ≥1024 px). Returns false when
   * there is no docked editor, so the chip falls back to its own dialog.
   */
  openFormula: (request: OpenFormulaRequest) => boolean;
  /** Long-press / context menu › Inspect: steps and fit for one formula. */
  inspectFormula: (expression: string) => void;
}

export const FormulaIdeContext = createContext<FormulaIdeBridge | null>(null);

export function useFormulaIdeBridge(): FormulaIdeBridge | null {
  return useContext(FormulaIdeContext);
}
