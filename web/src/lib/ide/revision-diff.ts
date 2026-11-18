import type { RevisionChangeRegion } from "@fiestaboard/ui";

export interface TemplateChange {
  /** 0-based row. */
  row: number;
  before: string;
  after: string;
}

/** Rows whose template text differs between two versions, top to bottom. */
export function changedRows(before: readonly string[], after: readonly string[]): TemplateChange[] {
  const rows = Math.max(before.length, after.length);
  const changes: TemplateChange[] = [];
  for (let row = 0; row < rows; row += 1) {
    const a = before[row] ?? "";
    const b = after[row] ?? "";
    if (a !== b) changes.push({ row, before: a, after: b });
  }
  return changes;
}

/** Full-width outline per changed row, as fractions of the overview (C43 RevisionDiff `changes`). */
export function changeRegions(changes: readonly TemplateChange[], boardRows: number): RevisionChangeRegion[] {
  if (boardRows < 1) return [];
  return changes
    .filter((change) => change.row < boardRows)
    .map((change) => ({ id: `row-${change.row}`, x: 0, y: change.row / boardRows, width: 1, height: 1 / boardRows }));
}
