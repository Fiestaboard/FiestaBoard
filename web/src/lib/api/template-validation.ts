// H4: POST /templates/validate at the board's real width (#1176). The route
// measures every line at the geometry the template renders at — the request's
// own device geometry, else the named board's grid — with variables at their
// longest, so the editor can show which lines the board will cut before it
// sends anything. Kept beside `templatesApi.validateTemplate` (syntax only,
// Flagship width) rather than changing that call's contract.

import { fetchApi } from "./core";
import type { GridSize, LineMetadata } from "./shared";

export type TemplateProblemCode =
  | "mismatched_braces"
  | "line_too_long"
  | "unknown_filter"
  | "unknown_source"
  | "unknown_field"
  | "formula"
  | "beyond_board"
  | "wrap_stopped";

export interface TemplateProblem {
  /** One-based template line. */
  line: number;
  /** Zero-based column; for `line_too_long` the board width, where the cut starts. */
  column: number;
  message: string;
  code: TemplateProblemCode;
  /** `line_too_long` only: the most tiles the line can render. */
  max_length: number | null;
}

export interface TemplateValidationAtResponse {
  valid: boolean;
  errors: TemplateProblem[];
  /** The geometry the hub validated at. */
  rows?: number;
  cols?: number;
}

export interface TemplateValidationTarget {
  template: string[];
  lineMetadata?: LineMetadata[];
  boardId?: string | null;
  deviceType?: string;
  notesWide?: number;
  notesTall?: number;
  grid?: GridSize | null;
}

export function validateTemplateAt(
  { template, lineMetadata, boardId, deviceType, notesWide, notesTall, grid }: TemplateValidationTarget,
  signal?: AbortSignal,
) {
  return fetchApi<TemplateValidationAtResponse>("/templates/validate", {
    method: "POST",
    body: JSON.stringify({
      template,
      ...(lineMetadata && { line_metadata: lineMetadata }),
      ...(boardId && { board_id: boardId }),
      ...(deviceType && { device_type: deviceType }),
      ...(deviceType === "note_array" && { notes_wide: notesWide ?? 1, notes_tall: notesTall ?? 1 }),
      ...(deviceType === "panel" && grid && { grid_rows: grid.rows, grid_cols: grid.cols }),
    }),
    signal,
  });
}
