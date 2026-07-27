import { memo } from "react";

import { COLOR_CODE_MAP } from "@/lib/board-colors";

/**
 * Minimal renderer for a raw board grid (int[][]) — used by the
 * transition preview harness, which receives frames as character codes
 * from the /transitions/preview endpoint.
 *
 * Unlike BoardDisplay/StaticBoardDisplay (which take a text string and
 * parse color markers), this component renders the codes directly and
 * skips the heavier decorative layers since the harness re-renders it
 * many times per second while scrubbing or playing a timeline.
 */

// Vestaboard character codes 0-62 (63-71 are color tiles, handled below).
const BOARD_CHARS: string[] = [
  " ",
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  ..."1234567890",
  "!",
  "@",
  "#",
  "$",
  "(",
  ")",
  " ",
  "-",
  " ",
  "+",
  "&",
  "=",
  ";",
  ":",
  " ",
  "'",
  '"',
  "%",
  ",",
  ".",
  " ",
  " ",
  "/",
  "?",
  " ",
  "°",
];

function codeToChar(code: number): string {
  if (code >= 0 && code < BOARD_CHARS.length) return BOARD_CHARS[code];
  return " ";
}

interface TransitionGridDisplayProps {
  grid: number[][];
  boardType?: "black" | "white";
  /** Size preset for the tiles. */
  size?: "sm" | "md";
  className?: string;
}

export const TransitionGridDisplay = memo(function TransitionGridDisplay({
  grid,
  boardType = "black",
  size = "md",
  className = "",
}: TransitionGridDisplayProps) {
  const isWhiteBoard = boardType === "white";
  const tileBg = isWhiteBoard ? "var(--color-board-surface-light)" : "var(--color-board-surface-dark)";
  const textColor = isWhiteBoard ? "var(--color-board-text-on-light)" : "var(--color-board-text-on-dark)";
  const bezelBg = isWhiteBoard ? "var(--color-board-bezel-light)" : "var(--color-board-bezel-dark)";
  const borderColor = isWhiteBoard ? "var(--color-board-bezel-border-light)" : "var(--color-board-bezel-border-dark)";

  const sizeClass = size === "sm" ? "w-[14px] h-[18px]" : "w-[20px] h-[28px] sm:w-[24px] sm:h-[34px]";
  const textSize = size === "sm" ? "text-[7px]" : "text-[10px] sm:text-[13px]";
  const gap = size === "sm" ? "gap-[3px]" : "gap-[2px] sm:gap-[4px]";
  const padding = size === "sm" ? "px-3 py-4" : "px-3 py-4 sm:px-5 sm:py-6";

  if (!grid.length) {
    return null;
  }

  return (
    <div className={`w-full flex justify-center ${className}`}>
      <div
        className="rounded-lg border-[3px] max-w-full overflow-x-auto"
        style={{ backgroundColor: bezelBg, borderColor, width: "fit-content" }}
      >
        <div
          className={`${padding} relative`}
          style={{
            background: isWhiteBoard
              ? "linear-gradient(135deg, var(--color-board-surface-light) 0%, var(--color-board-bezel-border-light) 100%)"
              : "linear-gradient(135deg, var(--color-board-surface-dark) 0%, var(--color-board-black) 100%)",
          }}
        >
          <div className={`flex flex-col ${gap}`}>
            {grid.map((row, r) => (
              <div key={r} className={`flex ${gap} justify-center`}>
                {row.map((code, c) => {
                  const colorBg = COLOR_CODE_MAP[String(code)];
                  if (colorBg !== undefined) {
                    return (
                      <div key={c} className={`${sizeClass} rounded-[3px]`} style={{ backgroundColor: colorBg }} />
                    );
                  }
                  const char = codeToChar(code);
                  return (
                    <div
                      key={c}
                      className={`${sizeClass} rounded-[3px] flex items-center justify-center`}
                      style={{ backgroundColor: tileBg }}
                    >
                      {char !== " " && (
                        <span
                          className={`${textSize} font-mono font-semibold select-none leading-none`}
                          style={{ color: textColor }}
                        >
                          {char}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
});
