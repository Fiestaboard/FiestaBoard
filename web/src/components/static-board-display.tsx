"use client";

import { useMemo, memo } from "react";
import { ALL_COLOR_CODES, BOARD_COLORS } from "@/lib/board-colors";
import type { DeviceType } from "@/lib/api";

const DEVICE_DIMS: Record<string, { rows: number; cols: number }> = {
  flagship: { rows: 6, cols: 22 },
  note: { rows: 3, cols: 15 },
};

const BOARD_CHARS = [
  ' ', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
  '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
  '!', '@', '#', '$', '(', ')', ' ', '-', ' ', '+', '&', '=', ';', ':',
  ' ', "'", '"', '%', ',', '.', ' ', ' ', '/', '?', ' ', '°',
  '63', '64', '65', '66', '67', '68', '69', '70', '71',
];

type Token = { type: "char"; value: string } | { type: "color"; code: string };

const COLOR_CODES = new Set(['63', '64', '65', '66', '67', '68', '69', '70', '71']);

function resolveColorCode(code: string, isWhiteBoard: boolean): string {
  if (isWhiteBoard) {
    if (code === "69" || code === "white") return BOARD_COLORS.black;
    if (code === "70" || code === "black") return BOARD_COLORS.white;
  }
  return ALL_COLOR_CODES[code] || BOARD_COLORS.black;
}

function parseLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < line.length) {
    if (line[i] === "{") {
      const closingBrace = line.indexOf("}", i);
      if (closingBrace !== -1) {
        const content = line.substring(i + 1, closingBrace);
        if (content.startsWith("/")) { i = closingBrace + 1; continue; }
        const contentLower = content.toLowerCase();
        let colorCode: string | null = null;
        if (ALL_COLOR_CODES[content]) colorCode = content;
        else if (ALL_COLOR_CODES[contentLower]) colorCode = contentLower;
        if (colorCode) { tokens.push({ type: "color", code: colorCode }); i = closingBrace + 1; continue; }
      }
    }
    tokens.push({ type: "char", value: line[i].toUpperCase() });
    i++;
  }
  return tokens;
}

function messageToGrid(message: string, rows: number, cols: number, deviceType: string): Token[][] {
  const lines = message.split("\n");
  const grid: Token[][] = [];
  const isNote = deviceType === "note";
  for (let row = 0; row < rows; row++) {
    const tokens = parseLine(lines[row] || "");
    const rowTokens: Token[] = [];
    for (let col = 0; col < cols; col++) {
      if (col < tokens.length) {
        const token = tokens[col];
        if (isNote && token.type === "char" && token.value === "°") {
          rowTokens.push({ type: "char", value: "♥" });
        } else {
          rowTokens.push(token);
        }
      } else {
        rowTokens.push({ type: "char", value: " " });
      }
    }
    grid.push(rowTokens);
  }
  return grid;
}

/**
 * Zero-overhead static board display for previews.
 * No useState, useEffect, useRef, or animation logic — renders a pure static
 * grid of divs. Each cell is a simple positioned element, eliminating the
 * ~8 hooks per CharTile that make the animated BoardDisplay expensive at scale.
 */
export const StaticBoardDisplay = memo(function StaticBoardDisplay({
  message,
  size = "sm",
  boardType = "black",
  deviceType = "flagship",
  className = "",
}: {
  message: string | null;
  size?: "sm" | "md" | "lg";
  boardType?: "black" | "white";
  deviceType?: DeviceType;
  className?: string;
}) {
  const dims = DEVICE_DIMS[deviceType] || DEVICE_DIMS.flagship;
  const isWhiteBoard = boardType === "white";
  const tileBg = isWhiteBoard ? "var(--color-board-surface-light)" : "var(--color-board-surface-dark)";
  const textColor = isWhiteBoard ? "var(--color-board-text-on-light)" : "var(--color-board-text-on-dark)";

  const grid = useMemo(
    () => messageToGrid(message ?? "", dims.rows, dims.cols, deviceType),
    [message, dims.rows, dims.cols, deviceType],
  );

  const sizeClasses: Record<string, string> = {
    sm: "w-[14px] h-[18px]",
    md: "w-[14px] h-[20px] sm:w-[20px] sm:h-[28px] md:w-[24px] md:h-[34px] lg:w-[28px] lg:h-[40px]",
    lg: "w-[18px] h-[26px] sm:w-[24px] sm:h-[34px] md:w-[28px] md:h-[40px] lg:w-[32px] lg:h-[46px]",
  };
  const textSizeClasses: Record<string, string> = {
    sm: "text-[7px]",
    md: "text-[7px] sm:text-[10px] md:text-[13px] lg:text-[16px]",
    lg: "text-[10px] sm:text-[13px] md:text-[16px] lg:text-[20px]",
  };
  const paddingClasses: Record<string, string> = {
    sm: "px-3 py-4",
    md: "px-2 py-3 sm:px-4 sm:py-6 md:px-5 md:py-8 lg:px-6 lg:py-10",
    lg: "px-3 py-4 sm:px-5 sm:py-7 md:px-6 md:py-9 lg:px-8 lg:py-12",
  };
  const gapClasses: Record<string, string> = {
    sm: "gap-[3px]",
    md: "gap-[2px] sm:gap-[4px] md:gap-[5px]",
    lg: "gap-[3px] sm:gap-[5px] md:gap-[6px] lg:gap-[7px]",
  };

  const bezelBg = isWhiteBoard ? "var(--color-board-bezel-light)" : "var(--color-board-bezel-dark)";
  const borderColor = isWhiteBoard ? "var(--color-board-bezel-border-light)" : "var(--color-board-bezel-border-dark)";
  // Simplified shadows for sm previews (14×18px tiles) — complex multi-layer
  // shadows are invisible at that scale and expensive to paint across 132+ tiles.
  const boxShadow = size === "sm"
    ? (isWhiteBoard
      ? "0 2px 8px rgba(0,0,0,0.1), inset 0 1px 2px rgba(255,255,255,0.9)"
      : "0 2px 8px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.06)")
    : (isWhiteBoard
      ? "0 8px 32px rgba(0,0,0,0.12), 0 4px 16px rgba(0,0,0,0.08), inset 0 1px 2px rgba(255,255,255,0.9), inset 0 0 0 1px rgba(255,255,255,0.5)"
      : "0 8px 32px rgba(0,0,0,0.6), 0 4px 16px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.08), inset 0 0 0 1px rgba(255,255,255,0.03)");
  const tileBoxShadow = size === "sm"
    ? (isWhiteBoard
      ? "0 1px 2px rgba(0,0,0,0.15)"
      : "0 1px 2px rgba(0,0,0,0.4)")
    : (isWhiteBoard
      ? "0 2px 4px rgba(0,0,0,0.2), inset 0 1px 2px rgba(0,0,0,0.1), inset 0 -1px 2px rgba(255,255,255,0.5), inset 1px 0 1px rgba(0,0,0,0.08), inset -1px 0 1px rgba(255,255,255,0.4)"
      : "0 2px 4px rgba(0,0,0,0.5), inset 0 1px 2px rgba(0,0,0,0.8), inset 0 -1px 1px rgba(255,255,255,0.08), inset 1px 0 1px rgba(0,0,0,0.5), inset -1px 0 1px rgba(255,255,255,0.05)");

  const borderClasses = size === "sm"
    ? "rounded-lg border-[3px]"
    : "rounded-lg sm:rounded-xl border-[3px] sm:border-[4px] lg:border-[5px]";

  return (
    <div className="w-full flex justify-center">
      <div
        role="img"
        aria-label={message ? `Board preview` : "Empty board"}
        className={`${borderClasses} ${className} max-w-full`}
        style={{ backgroundColor: bezelBg, borderColor, boxShadow, width: "fit-content" }}
      >
        <div
          className={`${paddingClasses[size]} relative`}
          aria-hidden="true"
          style={{
            background: isWhiteBoard
              ? "linear-gradient(135deg, var(--color-board-surface-light) 0%, var(--color-board-bezel-border-light) 100%)"
              : "linear-gradient(135deg, var(--color-board-surface-dark) 0%, var(--color-board-black) 100%)",
          }}
        >
          <div className={`flex flex-col ${gapClasses[size]}`}>
            {grid.map((row, rowIdx) => (
              <div key={rowIdx} className={`flex ${gapClasses[size]} justify-center`}>
                {row.map((token, colIdx) => {
                  if (token.type === "color") {
                    const bgColor = resolveColorCode(token.code, isWhiteBoard);
                    // sm previews: single div with color — decorative layers
                    // (inner shadow, separator line) are invisible at 14×18px.
                    if (size === "sm") {
                      return (
                        <div
                          key={colIdx}
                          className={`${sizeClasses[size]} rounded-[3px]`}
                          style={{ backgroundColor: bgColor, boxShadow: tileBoxShadow, contain: "layout style paint" }}
                        />
                      );
                    }
                    return (
                      <div
                        key={colIdx}
                        className={`relative ${sizeClasses[size]} rounded-[3px] overflow-hidden`}
                        style={{ backgroundColor: tileBg, boxShadow: tileBoxShadow, contain: "layout style paint" }}
                      >
                        <div
                          className="absolute rounded-[3px] overflow-hidden"
                          style={{
                            top: "3px", bottom: "4px", left: "1px", right: "1px",
                            backgroundColor: bgColor,
                            boxShadow: "0 2px 4px rgba(0,0,0,0.3), inset 0 1px 1px rgba(255,255,255,0.15), inset 0 -1px 1px rgba(0,0,0,0.25)",
                          }}
                        >
                          <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-black/10" />
                        </div>
                      </div>
                    );
                  }

                  const char = token.value;
                  const isHeart = char === "♥";

                  // sm previews: simplified tile — skip gradient overlay and
                  // separator line that are invisible at 14×18px. This cuts
                  // DOM nodes from ~4 to ~2 per tile (264→~132 fewer nodes
                  // per flagship board).
                  if (size === "sm") {
                    return (
                      <div
                        key={colIdx}
                        className={`${sizeClasses[size]} rounded-[3px] flex items-center justify-center`}
                        style={{ backgroundColor: tileBg, boxShadow: tileBoxShadow, contain: "layout style paint" }}
                      >
                        {char !== " " && (
                          <span
                            className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none`}
                            style={{ color: isHeart ? "#eb4034" : textColor }}
                          >
                            {char}
                          </span>
                        )}
                      </div>
                    );
                  }

                  return (
                    <div
                      key={colIdx}
                      className={`relative ${sizeClasses[size]} rounded-[3px] overflow-hidden`}
                      style={{ backgroundColor: tileBg, boxShadow: tileBoxShadow, contain: "layout style paint" }}
                    >
                      <div className="absolute inset-0 flex items-center justify-center" style={{ zIndex: 2 }}>
                        {char !== " " && (
                          <span
                            className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none`}
                            style={{ color: isHeart ? "#eb4034" : textColor }}
                          >
                            {char}
                          </span>
                        )}
                      </div>
                      <div
                        className={`absolute top-1/2 left-0 right-0 h-[1px] ${isWhiteBoard ? "bg-black/10" : "bg-black/30"}`}
                        style={{ zIndex: 3 }}
                      />
                      <div
                        className="absolute inset-0 pointer-events-none"
                        style={{
                          zIndex: 1,
                          background: isWhiteBoard
                            ? "linear-gradient(180deg, rgba(255,255,255,0.3) 0%, transparent 50%, rgba(0,0,0,0.05) 100%)"
                            : "linear-gradient(180deg, rgba(255,255,255,0.05) 0%, transparent 50%, rgba(0,0,0,0.2) 100%)",
                        }}
                      />
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
