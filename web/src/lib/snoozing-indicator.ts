// Snoozing indicator overlay logic for the home-page board preview.
//
// Mirrors the backend's `_build_silence_indicator_array` in `src/main.py`:
// places `indicatorText` at one of 5 positions (center | top-left | top-right
// | bottom-left | bottom-right) on a `numRows` x `numCols` board grid. Other
// rows and cells are preserved (color tokens etc.) so existing page content
// remains visible around the indicator.

type Token = { type: "char"; value: string } | { type: "color"; code: string };

export function parseLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < line.length) {
    if (line[i] === "{") {
      const closingBrace = line.indexOf("}", i);
      if (closingBrace !== -1) {
        const content = line.substring(i + 1, closingBrace);

        // Skip end tags {/...} or {/}
        if (content.startsWith("/")) {
          i = closingBrace + 1;
          continue;
        }

        // Check if it's a color code (63-70)
        const parsed = Number.parseInt(content, 10);
        if (/^\d+$/.test(content) && parsed >= 63 && parsed <= 70) {
          tokens.push({ type: "color", code: content });
          i = closingBrace + 1;
          continue;
        }
      }
    }

    // Convert to uppercase since board only supports uppercase letters
    tokens.push({ type: "char", value: line[i].toUpperCase() });
    i++;
  }

  return tokens;
}

export function tokensToString(tokens: Token[]): string {
  return tokens
    .map((token) => {
      if (token.type === "color") {
        return `{${token.code}}`;
      }
      return token.value;
    })
    .join("");
}

export type IndicatorPosition =
  | "center"
  | "top-left"
  | "top-right"
  | "bottom-left"
  | "bottom-right";

export function addSnoozingIndicator(
  content: string,
  numRows: number = 6,
  numCols: number = 22,
  indicatorText: string = "SNOOZING",
  position: IndicatorPosition = "center",
): string {
  const lines = content.split("\n");

  // Ensure we have exactly numRows lines (board rows)
  while (lines.length < numRows) {
    lines.push("");
  }

  // Truncate indicator to fit within the board width
  const indicator = indicatorText.slice(0, numCols);

  // Determine row and column based on position
  let targetRow: number;
  let startCol: number;
  if (position === "top-left") {
    targetRow = 0;
    startCol = 0;
  } else if (position === "top-right") {
    targetRow = 0;
    startCol = numCols - indicator.length;
  } else if (position === "bottom-left") {
    targetRow = numRows - 1;
    startCol = 0;
  } else if (position === "bottom-right") {
    targetRow = numRows - 1;
    startCol = numCols - indicator.length;
  } else {
    // center
    targetRow = Math.floor(numRows / 2);
    startCol = Math.max(0, Math.floor((numCols - indicator.length) / 2));
  }
  startCol = Math.max(0, startCol);

  const rowTokens = parseLine(lines[targetRow] || "");

  // Pad to numCols tokens total
  while (rowTokens.length < numCols) {
    rowTokens.push({ type: "char", value: " " });
  }

  // Truncate if too long
  const boardTokens = rowTokens.slice(0, numCols);

  for (let i = 0; i < indicator.length; i++) {
    boardTokens[startCol + i] = { type: "char", value: indicator[i] };
  }

  // Convert back to string
  lines[targetRow] = tokensToString(boardTokens);

  return lines.slice(0, numRows).join("\n");
}
