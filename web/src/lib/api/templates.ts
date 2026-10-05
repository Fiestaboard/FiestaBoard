// Templates domain: template variables/functions, validation and
// rendering, plus the Home Assistant entity catalog they draw on.

import { fetchApi } from "./core";
import type { GridSize, LineMetadata } from "./shared";

/** `grid_rows`/`grid_cols` body fields for a panel render (none when absent). */
function gridFields(grid?: GridSize | null): { grid_rows?: number; grid_cols?: number } {
  return grid ? { grid_rows: grid.rows, grid_cols: grid.cols } : {};
}

// Template types
export interface FormattingVariable {
  syntax: string;
  description: string;
}

export interface VariableMetadataEntry {
  description?: string;
  type?: "string" | "number" | "boolean" | "color";
  max_length?: number;
  group?: string;
  preview?: string;
  example?: string;
}

export interface VariableGroup {
  label: string;
}

export interface TemplateVariables {
  variables: Record<string, string[]>;
  max_lengths: Record<string, number>;
  variable_metadata?: Record<string, Record<string, VariableMetadataEntry>>;
  variable_groups?: Record<string, Record<string, VariableGroup>>;
  colors: Record<string, number>;
  symbols: string[];
  filters: string[];
  formatting: Record<string, FormattingVariable>;
  syntax_examples: Record<string, string>;
}

export interface HomeAssistantEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
  friendly_name: string;
}

export interface HomeAssistantEntitiesResponse {
  entities: HomeAssistantEntity[];
}

export interface FunctionSignatureEntry {
  category: string;
  signature: string;
  summary: string;
}

export interface FormulaFunctionsResponse {
  functions: Record<string, FunctionSignatureEntry>;
}

export interface TemplateValidationResponse {
  valid: boolean;
  errors: Array<{
    line: number;
    column: number;
    message: string;
  }>;
}

/**
 * One board cell as FiestaUI's `BoardToken` JSON — a rich cell (plan D15).
 * `type: "char"` carries `value`; `type: "color"` carries `code` (numeric,
 * `"63"`–`"71"`). `color` / `background` / `icon` appear only when set.
 */
export interface BoardTokenJson {
  type: "char" | "color";
  value?: string;
  code?: string;
  color?: string;
  background?: string;
  icon?: string;
}

/** Why a board's character set draws a cell differently from how it is written. */
export type CharsetIssueReason = "char" | "case" | "tile" | "icon" | "colorSpan" | "blockSpan";

/** One cell a board's character set cannot draw as written (FiestaUI `CharsetValidationIssue`). */
export interface CharsetIssue {
  row: number;
  col: number;
  token: BoardTokenJson;
  reason: CharsetIssueReason;
  /** What the board draws there instead. */
  fallback: BoardTokenJson;
}

export interface TemplateRenderResponse {
  rendered: string;
  lines: string[];
  line_count: number;
  /**
   * Present only when the request named a `board_id`: that board's character
   * set id, or `null` when it is unknown (a FiestaPanel).
   */
  charset?: string | null;
  /** With `charset`: every cell the board draws differently; `null` when unknown. */
  charset_issues?: CharsetIssue[] | null;
}

export interface TemplateRenderLiveResponse {
  rendered: string;
  lines: string[];
  line_count: number;
  sent_to_board: boolean;
  /** True when the send was skipped because the target board is paused. */
  paused: boolean;
  board_id: string | null;
}

export const templatesApi = {
  // Templates endpoints
  // `GET /v1/variables` is the merge of `GET /templates/variables` and
  // `GET /plugins/variables/all` (issue #1930). Both sides read the same
  // `registry.get_all_variables()` — `TemplateEngine.get_available_variables`
  // forwards to it — so the merge adds nothing to `variables`/`max_lengths`
  // and the payload here is a strict superset of the old one.
  getTemplateVariables: () => fetchApi<TemplateVariables>("/v1/variables"),
  getFormulaFunctions: () => fetchApi<FormulaFunctionsResponse>("/v1/functions"),
  validateTemplate: (template: string | string[]) =>
    fetchApi<TemplateValidationResponse>("/templates/validate", {
      method: "POST",
      body: JSON.stringify({ template }),
    }),
  // `notesWide`/`notesTall` are what size a `note_array` preview: its grid is
  // 15·notesWide by 3·notesTall, so omitting them made the server render every
  // array as one 3x15 Note and a `{{filled:-}}` line stopped a note short of
  // the board the same page filled correctly when sent (issue #2032). Ignored
  // by the server for `flagship` and `note`.
  //
  // `grid` sizes a `panel` (a FiestaPanel's explicit rows × cols): the server
  // answers 422 for a panel render without it. It is a trailing argument so
  // every existing positional caller keeps working; ignored for other types.
  //
  // `boardId` renders for that board (its extended markup when its output is
  // an LED one) and returns its `charset` / `charset_issues` for the editor's
  // warnings. Trailing and optional, so every existing caller is unchanged.
  renderTemplate: (
    template: string | string[],
    lineMetadata?: LineMetadata[],
    deviceType?: string,
    notesWide?: number,
    notesTall?: number,
    grid?: GridSize | null,
    boardId?: string | null,
  ) =>
    fetchApi<TemplateRenderResponse>("/templates/render", {
      method: "POST",
      body: JSON.stringify({
        template,
        ...(lineMetadata && { line_metadata: lineMetadata }),
        ...(deviceType && { device_type: deviceType }),
        ...(notesWide != null && { notes_wide: notesWide }),
        ...(notesTall != null && { notes_tall: notesTall }),
        ...gridFields(grid),
        ...(boardId && { board_id: boardId }),
      }),
    }),
  renderTemplateLive: (
    template: string | string[],
    boardId?: string,
    lineMetadata?: LineMetadata[],
    deviceType?: string,
    notesWide?: number,
    notesTall?: number,
    signal?: AbortSignal,
    grid?: GridSize | null,
  ) =>
    fetchApi<TemplateRenderLiveResponse>("/templates/render/live", {
      method: "POST",
      body: JSON.stringify({
        template,
        ...(boardId && { board_id: boardId }),
        ...(lineMetadata && { line_metadata: lineMetadata }),
        ...(deviceType && { device_type: deviceType }),
        ...(notesWide != null && { notes_wide: notesWide }),
        ...(notesTall != null && { notes_tall: notesTall }),
        ...gridFields(grid),
      }),
      signal,
    }),
  // Home Assistant endpoints
  getHomeAssistantEntities: () => fetchApi<HomeAssistantEntitiesResponse>("/home-assistant/entities"),
};
