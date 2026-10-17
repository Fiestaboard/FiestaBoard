/**
 * Convert a raw board grid (character codes, as returned in
 * `BoardCurrentMessageResponse.characters`) back into template lines that a
 * "template" page can store (issue #1945: save externally set board content
 * as a page).
 *
 * Codes 0-62 map to their literal characters (undefined slots become blanks);
 * color tiles 63-71 become `{{color}}` markers, which the template engine and
 * the editor both understand.
 */

import type { DeviceType, PageCreate } from "@/lib/api";

// Vestaboard character codes 0-62. Undefined placeholder slots are blanks.
const BOARD_CHARS: string[] = [
  " ",
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ", // 1-26
  ..."1234567890", // 27-36
  "!", // 37
  "@", // 38
  "#", // 39
  "$", // 40
  "(", // 41
  ")", // 42
  " ", // 43
  "-", // 44
  " ", // 45
  "+", // 46
  "&", // 47
  "=", // 48
  ";", // 49
  ":", // 50
  " ", // 51
  "'", // 52
  '"', // 53
  "%", // 54
  ",", // 55
  ".", // 56
  " ", // 57
  " ", // 58
  "/", // 59
  "?", // 60
  " ", // 61
  "°", // 62
];

const COLOR_NAMES: Record<number, string> = {
  63: "red",
  64: "orange",
  65: "yellow",
  66: "green",
  67: "blue",
  68: "violet",
  69: "white",
  70: "black",
  71: "black", // filled tile — closest color is black
};

function codeToCell(code: number): string {
  const color = COLOR_NAMES[code];
  if (color) return `{{${color}}}`;
  if (Number.isInteger(code) && code >= 0 && code < BOARD_CHARS.length) return BOARD_CHARS[code];
  return " ";
}

/** One template line per board row; trailing blanks are trimmed. */
export function boardCharactersToTemplate(characters: number[][]): string[] {
  return characters.map((row) => row.map(codeToCell).join("").replace(/ +$/, ""));
}

/**
 * A board's page geometry: what a template page saved from it must carry to
 * fit it. The shape ActivePageDisplay derives for the board it shows.
 */
export type BoardGeometry = {
  deviceType: DeviceType;
  notesWide: number;
  notesTall: number;
  gridRows?: number;
  gridCols?: number;
};

/**
 * The create-page body for "Save as page" (issue #1945): a template page whose
 * lines are *characters* and whose geometry is the board's, so the saved page
 * fits the board it came from. A note array carries its notes; a panel its
 * character grid, falling back to the grid's own size when the board has none
 * stored.
 */
export function buildBoardPageCreate(characters: number[][], geometry: BoardGeometry, name: string): PageCreate {
  return {
    name,
    type: "template",
    device_type: geometry.deviceType,
    template: boardCharactersToTemplate(characters),
    ...(geometry.deviceType === "note_array" && {
      notes_wide: geometry.notesWide,
      notes_tall: geometry.notesTall,
    }),
    ...(geometry.deviceType === "panel" && {
      grid_rows: geometry.gridRows ?? characters.length,
      grid_cols: geometry.gridCols ?? characters[0]?.length,
    }),
  };
}
