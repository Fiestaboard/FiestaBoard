import type { Dispatch, SetStateAction } from "react";

import type { CellSource, FormulaDiagnostic, FormulaTrace, RenderDiagnostics } from "@/lib/api/formula-debug";
import type { OriginDetail } from "@/lib/formula-ide/source-map";

import type { InspectFocus, OpenFormulaState } from "./use-formula-ide";

export interface WorkbenchProps {
  open: OpenFormulaState | null;
  setOpen: Dispatch<SetStateAction<OpenFormulaState | null>>;
  focus: InspectFocus | null;
  setFocus: Dispatch<SetStateAction<InspectFocus | null>>;
  inspect: boolean;
  /** 0-based loop iteration the steps and hints show. */
  iteration: number;
  formula: FormulaDiagnostic | undefined;
  cell: { origin: { index: number; source: CellSource } | null; detail: OriginDetail | null } | null;
  diagnostics: RenderDiagnostics | null;
  /** The rendered board rows. */
  rendered: string[];
  trace: FormulaTrace | null;
  traceLoading: boolean;
  traceFailed: boolean;
  sourceMapStatus: "complete" | "limit" | "not_requested" | null;
  renderFailed: boolean;
  boardCols: number;
  /** Docked under the preview (≥1024) or in the bottom sheet (640–1023); one editor, two placements (W-5). */
  placement?: "docked" | "sheet";
  /** Replace a formula body on a template line (one-tap fixes). */
  onReplaceFormula: (line: number, from: string, to: string) => void;
}
