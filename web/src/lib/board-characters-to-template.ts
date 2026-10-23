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
  71: "filled", // Distinct from black (70); preserve the observed flap.
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
