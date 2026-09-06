// Cross-domain primitives shared by several API domain modules:
// device/page geometry types and the generic action response.

export interface ActionResponse {
  status: string;
  message: string;
  debug_info?: string;
}

// Page types
export type PageType = "single" | "composite" | "template";

// Device types
export type DeviceType = "flagship" | "note" | "note_array";

/**
 * Which glyph a board's character-code-62 flap physically carries (issue #1657).
 *
 * Mirrors `Code62Glyph` in `src/devices.py` and the prop of the same shape in
 * `@fiestaboard/ui`. Declared here rather than re-exported from the package
 * because it is part of this app's API contract with its own backend.
 */
export type Code62Glyph = "degree" | "heart";

export interface RowConfig {
  source: string;
  row_index: number;
  target_row: number;
}

export type LineAlignment = "left" | "center" | "right";

export interface LineMetadata {
  alignment: LineAlignment;
  wrap: boolean;
}
