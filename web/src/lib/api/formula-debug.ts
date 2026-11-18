// Formula debugging on `POST /templates/render` (web 2.10, 04c).
//
// Three opt-in hub contracts ride on the ordinary preview render, never on
// `/templates/render/live` (the hub rejects them there, so an inspection can
// never reach a board):
// - H5 `diagnostics: true` → per-formula values and a per-line overflow report;
// - H6 `preview` → sample values, simulated missing data, a pinned clock and
//   cached plugin data, plus `sources` (freshness of the hub's own data);
// - H7 `debug` → one selected formula's execution trace and a per-cell source map.

import { fetchApi } from "./core";
import type { GridSize, LineMetadata } from "./shared";

/** H5: one `{{= … }}` formula as the render evaluated it. */
export interface FormulaDiagnostic {
  /** 1-based template line. */
  line: number;
  /** Code-point offset of the opening `{{=` in that line. */
  start: number;
  /** Offset just past the closing braces. */
  end: number;
  /** The formula body without the braces. */
  source: string;
  /** What the board shows; `\n`-joined rows for FOREACH. */
  value: string;
  /** `#REF`, `#VALUE`, `#DIV/0`, `#NAME?`, `#NUM`, `#SYNTAX` or null. */
  error: string | null;
  /** For `#SYNTAX`: the offset in `source`. */
  error_at: number | null;
  message: string | null;
  value_truncated?: boolean;
}

export type LineClip = "stopped_by_line" | "board_end" | "covered" | "beyond_board";

/** H5: what one template line produced on the board. */
export interface LineDiagnostic {
  line: number;
  /** 1-based board row it starts on; null when it shows nowhere. */
  first_row: number | null;
  rows_wanted: number;
  rows_shown: number;
  clip: LineClip | null;
  clip_line: number | null;
  /** Widest shown row, in drawn tiles. */
  widest: number;
  /** A shown row was wider than the board and so cut. */
  cut: boolean;
  /** Rendered text of the rows that did not land. */
  hidden: string[];
}

export interface RenderDiagnostics {
  formulas: FormulaDiagnostic[];
  /** Null for a bare string template or a page flowing around canvases. */
  lines: LineDiagnostic[] | null;
}

/** H6: the preview context. Every field is optional. */
export interface RenderPreviewContext {
  /** Sample values by variable path (`plugin.field`). */
  values?: Record<string, unknown>;
  /** Plugin ids or paths treated as unavailable. */
  missing?: string[];
  /** ISO 8601 instant the formula clock sees (`NOW()`, `TODAY()`). */
  at?: string;
  /** `cached` serves every plugin from its last result without fetching. */
  data?: "live" | "cached";
}

/** H6: freshness of the hub's own data for one plugin the render used. */
export interface PreviewSource {
  state: "fresh" | "stale" | "live" | "none";
  updated_at: string | null;
}

/** H7: one actual node execution in the selected formula. */
export interface FormulaTraceEvent {
  id: number;
  parent: number | null;
  kind: "literal" | "variable" | "unary" | "binary" | "call";
  label: string;
  /** Span in the formula body (`source`). */
  start: number;
  end: number;
  value: string;
  value_truncated: boolean;
  error: string | null;
}

export interface FormulaTrace extends FormulaDiagnostic {
  events: FormulaTraceEvent[];
  /** Executions were omitted (cap of 256). */
  truncated: boolean;
}

export type CellSourceKind = "literal" | "variable" | "formula" | "fill" | "markup";

/** H7: an authored span a board cell came from. */
export interface CellSource {
  line: number;
  start: number;
  end: number;
  kind: CellSourceKind;
}

export interface CellSourceMap {
  rows: number;
  cols: number;
  sources: CellSource[];
  /** `cells[row][col]` indexes `sources`, or null for layout padding. */
  cells: Array<Array<number | null>>;
}

export interface RenderDebug {
  trace: FormulaTrace | null;
  source_map: CellSourceMap | null;
  source_map_status: "complete" | "limit" | "not_requested";
}

export interface FormulaDebugRenderResponse {
  rendered: string;
  lines: string[];
  line_count: number;
  diagnostics?: RenderDiagnostics | null;
  debug?: RenderDebug | null;
  sources?: Record<string, PreviewSource> | null;
}

/** Everything that decides the board a template renders for. */
export interface RenderTarget {
  template: string[];
  lineMetadata?: LineMetadata[];
  deviceType?: string;
  notesWide?: number;
  notesTall?: number;
  grid?: GridSize | null;
  boardId?: string | null;
}

export interface FormulaDebugRequest {
  target: RenderTarget;
  preview?: RenderPreviewContext | null;
  /** H7: trace one formula by its H5 location and/or map every cell. */
  debug?: { trace?: { line: number; start: number } | null; sourceMap?: boolean } | null;
}

/** The JSON body for `POST /templates/render`; exported for tests. */
export function formulaDebugBody({ target, preview, debug }: FormulaDebugRequest): Record<string, unknown> {
  const body: Record<string, unknown> = { template: target.template, diagnostics: true };
  if (target.lineMetadata) body.line_metadata = target.lineMetadata;
  if (target.deviceType) body.device_type = target.deviceType;
  if (target.notesWide != null) body.notes_wide = target.notesWide;
  if (target.notesTall != null) body.notes_tall = target.notesTall;
  if (target.grid) {
    body.grid_rows = target.grid.rows;
    body.grid_cols = target.grid.cols;
  }
  if (target.boardId) body.board_id = target.boardId;
  if (preview && Object.keys(preview).length > 0) body.preview = preview;
  if (debug && (debug.trace || debug.sourceMap)) {
    body.debug = {
      ...(debug.trace ? { trace: { line: debug.trace.line, start: debug.trace.start } } : {}),
      ...(debug.sourceMap ? { source_map: true } : {}),
    };
  }
  return body;
}

export const formulaDebugApi = {
  render: (request: FormulaDebugRequest, signal?: AbortSignal) =>
    fetchApi<FormulaDebugRenderResponse>("/templates/render", {
      method: "POST",
      body: JSON.stringify(formulaDebugBody(request)),
      signal,
    }),
};
