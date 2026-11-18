// H7 per-cell source map: click a board cell, find the authored token (04c C3).

import type {
  CellSource,
  CellSourceMap,
  FormulaDiagnostic,
  LineDiagnostic,
  RenderDiagnostics,
} from "@/lib/api/formula-debug";

/** The authored source of a 0-based board cell, or null for layout padding. */
export function cellOrigin(map: CellSourceMap, row: number, col: number): { index: number; source: CellSource } | null {
  const index = map.cells[row]?.[col];
  if (index == null) return null;
  const source = map.sources[index];
  return source ? { index, source } : null;
}

/** 0-based board rows holding any cell from `index`. */
export function rowsForSource(map: CellSourceMap, index: number): number[] {
  const rows: number[] = [];
  map.cells.forEach((cells, row) => {
    if (cells.includes(index)) rows.push(row);
  });
  return rows;
}

export interface OriginDetail {
  formula?: FormulaDiagnostic;
  line?: LineDiagnostic;
  /** 1-based row within the formula's output (FOREACH item n). */
  rowInFormula: number | null;
}

/** The H5 formula and line behind a source, and which of its rows a 0-based board row is. */
export function originDetail(
  source: CellSource,
  diagnostics: RenderDiagnostics | null | undefined,
  row: number,
): OriginDetail {
  const formula =
    source.kind === "formula"
      ? diagnostics?.formulas.find((entry) => entry.line === source.line && entry.start === source.start)
      : undefined;
  const line = diagnostics?.lines?.find((entry) => entry.line === source.line);
  const rowInFormula = line?.first_row != null ? row + 1 - line.first_row + 1 : null;
  return { formula, line, rowInFormula: rowInFormula != null && rowInFormula >= 1 ? rowInFormula : null };
}
