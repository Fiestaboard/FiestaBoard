"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";

import { useBoardAnimationsEnabled } from "@/hooks/use-board-animations";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";
import { ALL_COLOR_CODES, BOARD_COLORS } from "@/lib/board-colors";
import { isNoteArray, NOTE_COLS, NOTE_ROWS, resolveDimensions } from "@/lib/board-dimensions";

// All displayable board characters indexed by character code (0-71).
// Undefined codes (43, 45, 51, 57, 58, 61) use ' ' as placeholder so
// array indices stay aligned with Vestaboard character codes.
const BOARD_CHARS = [
  " ", // 0  - Blank
  // A-Z (1-26)
  "A",
  "B",
  "C",
  "D",
  "E",
  "F",
  "G",
  "H",
  "I",
  "J",
  "K",
  "L",
  "M",
  "N",
  "O",
  "P",
  "Q",
  "R",
  "S",
  "T",
  "U",
  "V",
  "W",
  "X",
  "Y",
  "Z",
  // Numbers 1-9 (27-35), 0 (36)
  "1",
  "2",
  "3",
  "4",
  "5",
  "6",
  "7",
  "8",
  "9",
  "0",
  // Special characters (37-62), with placeholders for undefined codes
  "!", // 37
  "@", // 38
  "#", // 39
  "$", // 40
  "(", // 41
  ")", // 42
  " ", // 43 - undefined
  "-", // 44
  " ", // 45 - undefined
  "+", // 46
  "&", // 47
  "=", // 48
  ";", // 49
  ":", // 50
  " ", // 51 - undefined
  "'", // 52
  '"', // 53
  "%", // 54
  ",", // 55
  ".", // 56
  " ", // 57 - undefined
  " ", // 58 - undefined
  "/", // 59
  "?", // 60
  " ", // 61 - undefined
  "°", // 62 - Degree on Flagship, Heart on Note
  // Color tiles (63-71)
  "63",
  "64",
  "65",
  "66",
  "67",
  "68",
  "69",
  "70",
  "71",
];

// Extended characters that are not in BOARD_CHARS but can appear from device substitutions
const EXTRA_CHARS: Record<string, boolean> = { "♥": true };

function tokensEqual(a: Token, b: Token): boolean {
  if (a.type !== b.type) return false;
  if (a.type === "char" && b.type === "char") return a.value === b.value;
  if (a.type === "color" && b.type === "color") return a.code === b.code;
  return false;
}

// Backward compatibility alias
const _FIESTABOARD_CHARS = BOARD_CHARS;

// Check if a character is a color tile
const isColorTile = (char: string) => {
  return ["63", "64", "65", "66", "67", "68", "69", "70", "71"].includes(char);
};

// Resolve color code to hex value, accounting for white board inversion.
// On white Vestaboard hardware, white (69) and black (70) tiles are swapped.
function resolveColorCode(code: string, isWhiteBoard: boolean): string {
  if (isWhiteBoard) {
    if (code === "69" || code === "white") return BOARD_COLORS.black;
    if (code === "70" || code === "black") return BOARD_COLORS.white;
  }
  return ALL_COLOR_CODES[code] || BOARD_COLORS.black;
}

// Helper function to find character index in BOARD_CHARS array
function getCharIndex(char: string): number {
  const index = BOARD_CHARS.indexOf(char);
  return index >= 0 ? index : 0; // Default to space if not found
}

// Helper function to get character from token
function getCharFromToken(token: Token): string {
  if (token.type === "color") {
    return token.code; // Color tiles are represented by their code
  }
  return token.value;
}

// Parse a line into tokens (characters and color codes)
type Token = { type: "char"; value: string } | { type: "color"; code: string };

function parseLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < line.length) {
    // Check for single-bracket color markers: {63}, {red}, {/red}, {/}
    // (After template rendering, colors are normalized to single brackets)
    if (line[i] === "{") {
      const closingBrace = line.indexOf("}", i);
      if (closingBrace !== -1) {
        const content = line.substring(i + 1, closingBrace);

        // Check if it's an end tag {/...} or {/}
        if (content.startsWith("/")) {
          // Skip end tags - they don't render anything
          i = closingBrace + 1;
          continue;
        }

        // Check if it's a valid color code (numeric or named) - case insensitive
        const contentLower = content.toLowerCase();
        // Try exact match first (for numeric codes like "66"), then lowercase (for named colors)
        let colorCode: string | null = null;
        if (ALL_COLOR_CODES[content]) {
          colorCode = content;
        } else if (ALL_COLOR_CODES[contentLower]) {
          colorCode = contentLower;
        }

        if (colorCode) {
          tokens.push({ type: "color", code: colorCode });
          i = closingBrace + 1;
          continue;
        }
        // If not a valid color, fall through to treat { as regular character
      }
    }

    // Convert to uppercase since board only supports uppercase letters
    tokens.push({ type: "char", value: line[i].toUpperCase() });
    i++;
  }

  return tokens;
}

// Convert message string to grid of tokens with configurable dimensions
function messageToGrid(message: string, rows: number, cols: number, deviceType: string = "flagship"): Token[][] {
  const lines = message.split("\n");
  const grid: Token[][] = [];
  const isNote = deviceType === "note";

  for (let row = 0; row < rows; row++) {
    const line = lines[row] || "";
    const tokens = parseLine(line);
    const rowTokens: Token[] = [];

    // Fill to cols width
    for (let col = 0; col < cols; col++) {
      if (col < tokens.length) {
        const token = tokens[col];
        // On Note, degree symbol (code 62) displays as heart
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

// Shared CSS keyframes — injected once into the document head instead of
// being duplicated inside every CharTile render (~132 per board).
let keyframesInjected = false;
function ensureKeyframesInjected() {
  if (keyframesInjected || typeof document === "undefined") return;
  keyframesInjected = true;
  const style = document.createElement("style");
  style.setAttribute("data-board-keyframes", "");
  style.textContent = `
    @keyframes flapDown { from { transform: rotateX(0deg); } to { transform: rotateX(-90deg); } }
    @keyframes flapUp { from { transform: rotateX(90deg); } to { transform: rotateX(0deg); } }
    @keyframes flapShadow { 0%, 100% { opacity: 0; } 50% { opacity: 1; } }
  `;
  document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// Static rendering path — used for non-animated previews (e.g. chat cards).
// No useState / useEffect / useRef per tile, so React pays zero scheduling
// cost for the ~132 tiles of a static board.
// ---------------------------------------------------------------------------

const StaticTile = memo(function StaticTile({
  token,
  size,
  boardType,
}: {
  token: Token;
  size: "sm" | "md" | "lg";
  boardType: "black" | "white";
}) {
  const isWhiteBoard = boardType === "white";
  const tileBg = isWhiteBoard ? "var(--color-board-surface-light)" : "var(--color-board-surface-dark)";
  const textColor = isWhiteBoard ? "var(--color-board-text-on-light)" : "var(--color-board-text-on-dark)";

  const sizeClass =
    size === "sm"
      ? "w-[14px] h-[18px]"
      : size === "md"
        ? "w-[14px] h-[20px] sm:w-[20px] sm:h-[28px] md:w-[24px] md:h-[34px] lg:w-[28px] lg:h-[40px]"
        : "w-[18px] h-[26px] sm:w-[24px] sm:h-[34px] md:w-[28px] md:h-[40px] lg:w-[32px] lg:h-[46px]";

  const textSizeClass =
    size === "sm"
      ? "text-[7px]"
      : size === "md"
        ? "text-[7px] sm:text-[10px] md:text-[13px] lg:text-[16px]"
        : "text-[10px] sm:text-[13px] md:text-[16px] lg:text-[20px]";

  const splitLine = (
    <div className={`absolute top-1/2 left-0 right-0 h-[1px] ${isWhiteBoard ? "bg-black/10" : "bg-black/30"}`} />
  );

  if (token.type === "color") {
    const bgColor = resolveColorCode(token.code, isWhiteBoard);
    const inset = size === "sm" ? "3px 1px 4px" : size === "md" ? "4px 2px 5px" : "5px 2px 6px";
    return (
      <div className={`${sizeClass} relative rounded-[3px] overflow-hidden`} style={{ backgroundColor: tileBg }}>
        <div className="absolute rounded-[2px]" style={{ inset, backgroundColor: bgColor }} />
        {splitLine}
      </div>
    );
  }

  const displayChar = EXTRA_CHARS[token.value] ? token.value : BOARD_CHARS[getCharIndex(token.value)];
  const isBlank = displayChar === " ";

  return (
    <div
      className={`${sizeClass} relative rounded-[3px] overflow-hidden flex items-center justify-center`}
      style={{ backgroundColor: tileBg }}
    >
      {!isBlank && (
        <span
          className={`${textSizeClass} font-mono font-semibold select-none leading-none`}
          style={{ color: token.value === "♥" ? "#eb4034" : textColor }}
        >
          {displayChar}
        </span>
      )}
      {splitLine}
    </div>
  );
});

const StaticGridRow = memo(function StaticGridRow({
  row,
  rowIdx,
  size,
  gapClass,
  boardType,
  showSeams = false,
  isRowSeam = false,
  seamGap = "6px",
}: {
  row: Token[];
  rowIdx: number;
  size: "sm" | "md" | "lg";
  gapClass: string;
  boardType: "black" | "white";
  showSeams?: boolean;
  isRowSeam?: boolean;
  seamGap?: string;
}) {
  return (
    <div
      data-note-row=""
      {...(isRowSeam ? { "data-note-row-seam": "true" } : {})}
      className={`flex ${gapClass} justify-center`}
      style={isRowSeam ? { marginTop: seamGap } : undefined}
    >
      {row.map((token, colIdx) => {
        const isColSeam = showSeams && colIdx > 0 && colIdx % NOTE_COLS === 0;
        return (
          <div
            key={`col-${rowIdx}-${colIdx}`}
            data-note-tile=""
            {...(isColSeam ? { "data-note-col-seam": "true" } : {})}
            style={isColSeam ? { marginLeft: seamGap } : undefined}
          >
            <StaticTile token={token} size={size} boardType={boardType} />
          </div>
        );
      })}
    </div>
  );
});

// ---------------------------------------------------------------------------
// Animated rendering path (original)
// ---------------------------------------------------------------------------

// Memoized grid row component to prevent row-level re-renders
const GridRow = memo(
  function GridRow({
    row,
    rowIdx,
    size,
    gapClass,
    boardType = "black",
    isAnimating = false,
    animationsEnabled = true,
    showSeams = false,
    isRowSeam = false,
    seamGap = "6px",
  }: {
    row: Token[];
    rowIdx: number;
    size: "sm" | "md" | "lg";
    gapClass: string;
    boardType?: "black" | "white";
    isAnimating?: boolean;
    animationsEnabled?: boolean;
    showSeams?: boolean;
    isRowSeam?: boolean;
    seamGap?: string;
  }) {
    return (
      <div
        data-note-row=""
        {...(isRowSeam ? { "data-note-row-seam": "true" } : {})}
        className={`flex ${gapClass} justify-center`}
        style={isRowSeam ? { marginTop: seamGap } : undefined}
      >
        {row.map((token, colIdx) => {
          const isColSeam = showSeams && colIdx > 0 && colIdx % NOTE_COLS === 0;
          return (
            <div
              key={`col-${rowIdx}-${colIdx}`}
              data-note-tile=""
              {...(isColSeam ? { "data-note-col-seam": "true" } : {})}
              style={isColSeam ? { marginLeft: seamGap } : undefined}
            >
              <CharTile
                token={token}
                size={size}
                boardType={boardType}
                isAnimating={isAnimating}
                animationsEnabled={animationsEnabled}
                rowIdx={rowIdx}
                colIdx={colIdx}
              />
            </div>
          );
        })}
      </div>
    );
  },
  (prevProps, nextProps) => {
    // Only re-render if row data changes
    if (prevProps.row.length !== nextProps.row.length) return false;
    if (prevProps.size !== nextProps.size) return false;
    if (prevProps.gapClass !== nextProps.gapClass) return false;
    if (prevProps.boardType !== nextProps.boardType) return false;
    if (prevProps.isAnimating !== nextProps.isAnimating) return false;
    if (prevProps.animationsEnabled !== nextProps.animationsEnabled) return false;
    if (prevProps.showSeams !== nextProps.showSeams) return false;
    if (prevProps.isRowSeam !== nextProps.isRowSeam) return false;
    if (prevProps.seamGap !== nextProps.seamGap) return false;

    // Deep compare tokens
    for (let i = 0; i < prevProps.row.length; i++) {
      if (!tokensEqual(prevProps.row[i], nextProps.row[i])) return false;
    }

    return true; // Rows are equal, don't re-render
  },
);

// Individual character tile component - memoized to prevent unnecessary re-renders
// Now pre-renders all 71 characters and uses CSS to show/hide them
const CharTile = memo(
  function CharTile({
    token,
    size = "md",
    boardType = "black",
    isAnimating: rawIsAnimating = false,
    animationsEnabled = true,
    rowIdx = 0,
    colIdx = 0,
  }: {
    token: Token;
    size?: "sm" | "md" | "lg";
    boardType?: "black" | "white";
    isAnimating?: boolean;
    animationsEnabled?: boolean;
    rowIdx?: number;
    colIdx?: number;
  }) {
    // When the user disables board animations (or reduce_motion is on),
    // collapse isAnimating so the loading rotation never starts and the
    // 4-layer flap structure (~4 extra DOM nodes per tile) never renders.
    // The transition effect below also short-circuits to snap tiles to
    // their target instantly.
    const isAnimating = animationsEnabled && rawIsAnimating;
    const sizeClasses = {
      sm: "w-[14px] h-[18px]", // Small previews stay fixed size
      md: "w-[14px] h-[20px] sm:w-[20px] sm:h-[28px] md:w-[24px] md:h-[34px] lg:w-[28px] lg:h-[40px]", // Responsive
      lg: "w-[18px] h-[26px] sm:w-[24px] sm:h-[34px] md:w-[28px] md:h-[40px] lg:w-[32px] lg:h-[46px]", // Responsive
    };

    const textSizeClasses = {
      sm: "text-[7px]", // Small previews stay fixed size
      md: "text-[7px] sm:text-[10px] md:text-[13px] lg:text-[16px]", // Responsive
      lg: "text-[10px] sm:text-[13px] md:text-[16px] lg:text-[20px]", // Responsive
    };

    // White board inverts character text colors
    const isWhiteBoard = boardType === "white";
    const tileBg = isWhiteBoard ? "var(--color-board-surface-light)" : "var(--color-board-surface-dark)";
    const textColor = isWhiteBoard ? "var(--color-board-text-on-light)" : "var(--color-board-text-on-dark)";

    // Get target character index
    const targetChar = getCharFromToken(token);
    const targetCharIndex = getCharIndex(targetChar);

    // All tiles flip in sync - same duration, no random delay
    const animationDuration = 80; // ms per character step — matches Vestaboard "Fast" mode (~60 RPM, 62 flaps)
    const _delay = 0; // All tiles start at the same time

    // State for current character index during animation
    // Always start from target character - tiles are set by the parent component
    // Tiles should only rotate when: loading, or transitioning to a new character
    const [currentCharIndex, setCurrentCharIndex] = useState(() => targetCharIndex);

    // State to track if we're transitioning to a new target
    const [isTransitioning, setIsTransitioning] = useState(false);

    // Refs for interval and target tracking
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const prevTargetCharIndexRef = useRef(targetCharIndex);
    const prevIsAnimatingRef = useRef(isAnimating);
    const currentCharIndexRef = useRef(currentCharIndex);
    const justStoppedLoadingRef = useRef(false);

    // Update currentCharIndexRef when currentCharIndex changes
    useEffect(() => {
      currentCharIndexRef.current = currentCharIndex;
    }, [currentCharIndex]);

    // Effect 1: Handle loading animation (isAnimating prop)
    useEffect(() => {
      const wasAnimating = prevIsAnimatingRef.current;
      prevIsAnimatingRef.current = isAnimating;

      // If animations are disabled (user setting or reduce-motion), short-circuit:
      // clear any running interval and snap to target without rotating.
      if (!animationsEnabled) {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        setIsTransitioning(false);
        setCurrentCharIndex(targetCharIndex);
        prevTargetCharIndexRef.current = targetCharIndex;
        justStoppedLoadingRef.current = false;
        return;
      }

      if (isAnimating) {
        // Loading state: cycle through all characters continuously
        // Don't reset to target - just continue from current position
        setIsTransitioning(false);

        // Clear any existing interval
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }

        // If we just started animating, start from current position
        // Otherwise continue from where we are
        if (!wasAnimating) {
          // Just started - reset to target to begin cycle
          setCurrentCharIndex(targetCharIndex);
        }

        // Cycle through all characters in order, one per tick
        // Continue cycling indefinitely while isAnimating is true
        intervalRef.current = setInterval(() => {
          setCurrentCharIndex((prev) => (prev + 1) % BOARD_CHARS.length);
        }, animationDuration);

        return () => {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        };
      } else if (wasAnimating) {
        // Just stopped loading - transition from current position to target
        // Mark that we just stopped loading so Effect 2 doesn't interfere initially
        justStoppedLoadingRef.current = true;

        // Clear any existing interval first
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }

        // Check if target changed from what it was before loading
        const prevTarget = prevTargetCharIndexRef.current;
        const currentTarget = targetCharIndex;
        const targetChanged = prevTarget !== currentTarget;

        // Update target ref
        prevTargetCharIndexRef.current = currentTarget;

        // Check if we're already at the current target
        const currentIndex = currentCharIndexRef.current;
        if (currentIndex === currentTarget) {
          // Already at target - no transition needed
          // If target didn't change, tile stays static (correct - only changed tiles transition)
          // Update ref first to ensure consistency
          currentCharIndexRef.current = currentTarget;
          // Ensure state is consistent to avoid flashing
          setIsTransitioning(false);
          // Use functional update to ensure we don't trigger unnecessary re-renders
          setCurrentCharIndex((prev) => (prev === currentTarget ? prev : currentTarget));
          justStoppedLoadingRef.current = false;
          return;
        }

        // Only transition if target actually changed
        // If target didn't change, we should already be at target (from loading)
        // So if we're not at target and target didn't change, something went wrong - just set it
        if (!targetChanged) {
          // Target didn't change but we're not at target - set it directly (no transition)
          // Update ref first to ensure consistency
          currentCharIndexRef.current = currentTarget;
          // Then update state - use functional update to avoid unnecessary re-renders
          setCurrentCharIndex((prev) => {
            if (prev === currentTarget) {
              return prev; // Already correct, no change needed
            }
            return currentTarget; // Update to target
          });
          // Ensure transition state is false before state updates complete
          setIsTransitioning(false);
          justStoppedLoadingRef.current = false;
          return;
        }

        // Target changed - transition from current position to new target
        // This is the only case where we transition: when the target character actually changed
        setIsTransitioning(true);

        // Helper function to advance character and check for target
        // Use ref to avoid stale closures
        const advanceToTarget = () => {
          setCurrentCharIndex((current) => {
            const target = prevTargetCharIndexRef.current;

            // If already at target, stop transitioning
            if (current === target) {
              setIsTransitioning(false);
              justStoppedLoadingRef.current = false; // Clear the flag
              if (intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
              }
              return current;
            }

            // Continue cycling forward
            const next = (current + 1) % BOARD_CHARS.length;
            // If we've reached the target, stop transitioning
            if (next === target) {
              setIsTransitioning(false);
              justStoppedLoadingRef.current = false; // Clear the flag when we reach target
              if (intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
              }
              return next;
            }
            return next;
          });
        };

        // Immediately advance once to start the transition
        advanceToTarget();

        // Then start interval for subsequent ticks
        intervalRef.current = setInterval(advanceToTarget, animationDuration);

        return () => {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          justStoppedLoadingRef.current = false; // Clear flag on cleanup
        };
      } else {
        // Not animating and wasn't animating - ensure we're at target
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        setIsTransitioning(false);
        // Use functional update to avoid unnecessary re-renders if already at target
        setCurrentCharIndex((prev) => (prev === targetCharIndex ? prev : targetCharIndex));
      }
    }, [isAnimating, targetCharIndex, animationDuration, animationsEnabled]); // Include targetCharIndex so we can transition to it when loading stops

    // Effect 2: Handle target character changes - independent transition
    useEffect(() => {
      // If animations are disabled, snap directly to the target — no flap,
      // no rotation through intermediate characters.
      if (!animationsEnabled) {
        prevTargetCharIndexRef.current = targetCharIndex;
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        setIsTransitioning(false);
        setCurrentCharIndex(targetCharIndex);
        return;
      }

      // If we're transitioning from loading, update the target ref so Effect 1 uses the new target
      if (justStoppedLoadingRef.current) {
        // Update the target ref so Effect 1's transition uses the new target
        prevTargetCharIndexRef.current = targetCharIndex;
        return;
      }

      // CRITICAL: Don't do anything if we're in loading state OR transitioning
      // The loading animation (Effect 1) handles everything during/after loading
      if (isAnimating || isTransitioning) {
        // Just update the ref but don't interfere
        prevTargetCharIndexRef.current = targetCharIndex;
        return;
      }

      const prevTarget = prevTargetCharIndexRef.current;
      const currentTarget = targetCharIndex;

      // If target changed, start transitioning to new target
      if (prevTarget !== currentTarget) {
        // Update ref
        prevTargetCharIndexRef.current = currentTarget;

        // Check if we're already at the new target
        const currentIndex = currentCharIndexRef.current;
        if (currentIndex === currentTarget) {
          // Already at target, no transition needed
          setIsTransitioning(false);
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          // Make sure currentCharIndex state matches
          setCurrentCharIndex(currentTarget);
          return;
        }

        // Start transitioning to new target
        setIsTransitioning(true);

        // Clear any existing interval
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }

        // Helper function to advance character and check for target
        // Uses refs to avoid stale closures
        const advanceToTarget = () => {
          setCurrentCharIndex((current) => {
            const target = prevTargetCharIndexRef.current;

            // If already at target, stop transitioning
            if (current === target) {
              setIsTransitioning(false);
              if (intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
              }
              return current;
            }

            // Continue cycling forward
            const next = (current + 1) % BOARD_CHARS.length;
            // If we've reached the target, stop transitioning
            if (next === target) {
              setIsTransitioning(false);
              if (intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
              }
              return next;
            }
            return next;
          });
        };

        // Immediately advance once to start the transition
        advanceToTarget();

        // Then start interval for subsequent ticks
        intervalRef.current = setInterval(advanceToTarget, animationDuration);

        return () => {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        };
      } else {
        // Target hasn't changed - ensure we're at target and not transitioning
        // Tiles should only transition when target changes or coming out of loading
        if (currentCharIndexRef.current !== currentTarget) {
          // Not at target but target hasn't changed - just set it directly
          // This shouldn't happen normally, but handle it gracefully
          setCurrentCharIndex(currentTarget);
        }
        setIsTransitioning(false);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    }, [targetCharIndex, isAnimating, isTransitioning, animationDuration, animationsEnabled]);

    // Enhanced 3D shadows for flip tile effect
    const boxShadow = isWhiteBoard
      ? `
      0 2px 4px rgba(0,0,0,0.2),
      inset 0 1px 2px rgba(0,0,0,0.1),
      inset 0 -1px 2px rgba(255,255,255,0.5),
      inset 1px 0 1px rgba(0,0,0,0.08),
      inset -1px 0 1px rgba(255,255,255,0.4)
    `
      : `
      0 2px 4px rgba(0,0,0,0.5),
      inset 0 1px 2px rgba(0,0,0,0.8),
      inset 0 -1px 1px rgba(255,255,255,0.08),
      inset 1px 0 1px rgba(0,0,0,0.5),
      inset -1px 0 1px rgba(255,255,255,0.05)
    `;

    // Color tiles also animate - they cycle through all characters during loading
    // No special handling needed - they go through the same animation logic below

    const currentChar = BOARD_CHARS[currentCharIndex];
    const prevCharIndex = (currentCharIndex - 1 + BOARD_CHARS.length) % BOARD_CHARS.length;
    const prevChar = BOARD_CHARS[prevCharIndex];

    ensureKeyframesInjected();

    return (
      <>
        <div
          className={`relative ${sizeClasses[size]} rounded-[3px] overflow-hidden`}
          data-testid={`char-tile-${rowIdx}-${colIdx}`}
          data-current-char={currentChar}
          data-target-char={targetChar}
          data-is-animating={isAnimating}
          data-is-transitioning={isTransitioning}
          style={{
            backgroundColor: tileBg,
            boxShadow,
            contain: "layout style paint",
            ...(isAnimating || isTransitioning ? { perspective: "800px", isolation: "isolate" } : {}),
          }}
        >
          {/* Static display - show target character when not animating and not transitioning */}
          {!isAnimating &&
            !isTransitioning &&
            (() => {
              // If token is a color tile, always render as color tile (not character)
              if (token.type === "color") {
                const bgColor = resolveColorCode(token.code, isWhiteBoard);
                const marginClasses =
                  size === "sm"
                    ? "[--color-margin-top:3px] [--color-margin-bottom:4px] [--color-margin-h:1px]"
                    : size === "md"
                      ? "[--color-margin-top:3px] sm:[--color-margin-top:4px] md:[--color-margin-top:5px] lg:[--color-margin-top:6px] [--color-margin-bottom:4px] sm:[--color-margin-bottom:6px] md:[--color-margin-bottom:7px] lg:[--color-margin-bottom:8px] [--color-margin-h:1px] sm:[--color-margin-h:2px]"
                      : "[--color-margin-top:4px] sm:[--color-margin-top:5px] md:[--color-margin-top:6px] lg:[--color-margin-top:8px] [--color-margin-bottom:5px] sm:[--color-margin-bottom:7px] md:[--color-margin-bottom:8px] lg:[--color-margin-bottom:10px] [--color-margin-h:2px] md:[--color-margin-h:3px]";

                return (
                  <div
                    key={`static-color-${token.code}`}
                    className={`absolute inset-0 ${marginClasses} flex items-center justify-center`}
                    style={{ zIndex: 2 }}
                  >
                    <div
                      className="relative rounded-[3px] overflow-hidden"
                      style={{
                        marginTop: "var(--color-margin-top)",
                        marginBottom: "var(--color-margin-bottom)",
                        marginLeft: "var(--color-margin-h)",
                        marginRight: "var(--color-margin-h)",
                        width: "calc(100% - (var(--color-margin-h) * 2))",
                        height: "calc(100% - (var(--color-margin-top) + var(--color-margin-bottom)))",
                        backgroundColor: bgColor,
                        boxShadow: `
                      0 2px 4px rgba(0,0,0,0.3),
                      inset 0 1px 1px rgba(255,255,255,0.15),
                      inset 0 -1px 1px rgba(0,0,0,0.25),
                      inset 1px 0 1px rgba(255,255,255,0.1),
                      inset -1px 0 1px rgba(0,0,0,0.2)
                    `,
                      }}
                    >
                      <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-black/10" />
                    </div>
                  </div>
                );
              }

              // Regular character tile
              // Use original token value for extended chars (like ♥ on Note) that aren't in BOARD_CHARS
              const originalChar = getCharFromToken(token);
              const targetChar = EXTRA_CHARS[originalChar] ? originalChar : BOARD_CHARS[targetCharIndex];
              const isColor = isColorTile(targetChar);
              const charBg = isColor ? resolveColorCode(targetChar, isWhiteBoard) : tileBg;
              // Heart character should render in red
              const isHeart = targetChar === "♥";
              const charColor = isHeart ? "#eb4034" : textColor;

              return (
                <div
                  key={`static-char-${targetCharIndex}`}
                  className="absolute inset-0 flex items-center justify-center overflow-hidden"
                  style={{
                    zIndex: 2,
                    backgroundColor: charBg,
                    marginLeft: isColor ? "-4px" : 0,
                    marginRight: isColor ? "-4px" : 0,
                  }}
                >
                  {!isColor && targetChar !== " " && (
                    <span
                      className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none relative z-10`}
                      style={{ color: charColor }}
                    >
                      {targetChar}
                    </span>
                  )}
                  {/* Blank/space character - render as empty but maintain layout */}
                  {!isColor && targetChar === " " && (
                    <span
                      className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none relative z-10`}
                      style={{ color: textColor, visibility: "hidden" }}
                      aria-hidden="true"
                    >
                      {" "}
                    </span>
                  )}
                  {isColor && (
                    <div
                      className="absolute inset-0 rounded-[3px]"
                      style={{
                        backgroundColor: charBg,
                        boxShadow: `
                      0 2px 4px rgba(0,0,0,0.3),
                      inset 0 1px 1px rgba(255,255,255,0.15),
                      inset 0 -1px 1px rgba(0,0,0,0.25),
                      inset 1px 0 1px rgba(255,255,255,0.1),
                      inset -1px 0 1px rgba(0,0,0,0.2)
                    `,
                      }}
                    />
                  )}
                </div>
              );
            })()}

          {/* 3D split-flap animation — 4-layer structure per tile:
            1. Static new top half (revealed behind falling flap)
            2. Static old bottom half (covered by unfolding flap)
            3. Top flap: old char top, folds down past midpoint (gravity ease-in)
            4. Bottom flap: new char bottom, unfolds into place (settling ease-out) */}
          {(isAnimating || isTransitioning) &&
            (() => {
              const newChar = currentChar;
              const flipDur = animationDuration;
              const topDur = Math.round(flipDur * 0.55);
              const botDelay = Math.round(flipDur * 0.35);
              const botDur = Math.round(flipDur * 0.55);

              const renderHalf = (char: string, isTop: boolean) => {
                const isColor = isColorTile(char);
                const bg = isColor ? resolveColorCode(char, isWhiteBoard) : tileBg;
                const isHeart = char === "♥";
                return (
                  <div
                    style={{
                      position: "absolute" as const,
                      ...(isTop ? { top: 0 } : { bottom: 0 }),
                      left: 0,
                      right: 0,
                      height: "200%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      backgroundColor: bg,
                    }}
                  >
                    {!isColor && char !== " " && (
                      <span
                        className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none`}
                        style={{ color: isHeart ? "#eb4034" : textColor }}
                      >
                        {char}
                      </span>
                    )}
                  </div>
                );
              };

              return (
                <>
                  {/* Layer 1: new char top half — sits behind falling top flap */}
                  <div
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      right: 0,
                      height: "50%",
                      overflow: "hidden",
                      zIndex: 1,
                    }}
                  >
                    {renderHalf(newChar, true)}
                  </div>

                  {/* Layer 2: old char bottom half — sits behind unfolding bottom flap */}
                  <div
                    style={{
                      position: "absolute",
                      top: "50%",
                      left: 0,
                      right: 0,
                      height: "50%",
                      overflow: "hidden",
                      zIndex: 1,
                    }}
                  >
                    {renderHalf(prevChar, false)}
                  </div>

                  {/* Layer 3: top flap — old char top half, folds DOWN (hinged at midpoint) */}
                  <div
                    key={`ft-${currentCharIndex}`}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      right: 0,
                      height: "50%",
                      overflow: "hidden",
                      zIndex: 3,
                      transformOrigin: "bottom center",
                      backfaceVisibility: "hidden",
                      willChange: "transform",
                      animation: `flapDown ${topDur}ms ease-in forwards`,
                    }}
                  >
                    {renderHalf(prevChar, true)}
                    {/* Hinge shadow at bottom edge of flap */}
                    <div
                      style={{
                        position: "absolute",
                        bottom: 0,
                        left: 0,
                        right: 0,
                        height: "30%",
                        background: "linear-gradient(to bottom, transparent, rgba(0,0,0,0.12))",
                        pointerEvents: "none",
                      }}
                    />
                  </div>

                  {/* Layer 4: bottom flap — new char bottom half, UNFOLDS into place */}
                  <div
                    key={`fb-${currentCharIndex}`}
                    style={{
                      position: "absolute",
                      top: "50%",
                      left: 0,
                      right: 0,
                      height: "50%",
                      overflow: "hidden",
                      zIndex: 2,
                      transformOrigin: "top center",
                      backfaceVisibility: "hidden",
                      willChange: "transform",
                      transform: "rotateX(90deg)",
                      animation: `flapUp ${botDur}ms cubic-bezier(0.33, 0, 0.15, 1) ${botDelay}ms forwards`,
                    }}
                  >
                    {renderHalf(newChar, false)}
                    {/* Hinge highlight at top edge of flap */}
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "30%",
                        background: isWhiteBoard
                          ? "linear-gradient(to bottom, rgba(0,0,0,0.06), transparent)"
                          : "linear-gradient(to bottom, rgba(0,0,0,0.15), transparent)",
                        pointerEvents: "none",
                      }}
                    />
                  </div>

                  {/* Shadow cast by falling flap onto bottom half */}
                  <div
                    key={`fs-${currentCharIndex}`}
                    style={{
                      position: "absolute",
                      top: "50%",
                      left: 0,
                      right: 0,
                      height: "50%",
                      background: isWhiteBoard
                        ? "linear-gradient(to bottom, rgba(0,0,0,0.06), transparent)"
                        : "linear-gradient(to bottom, rgba(0,0,0,0.3), transparent)",
                      zIndex: 4,
                      pointerEvents: "none",
                      opacity: 0,
                      animation: `flapShadow ${flipDur}ms ease-in-out forwards`,
                    }}
                  />

                  {/* Split line at midpoint */}
                  <div
                    className={`absolute top-1/2 left-0 right-0 h-[1px] ${isWhiteBoard ? "bg-black/10" : "bg-black/30"}`}
                    style={{ zIndex: 5 }}
                  />
                </>
              );
            })()}

          {/* Static display - when not animating and not transitioning AND we're at target */}
          {/* Character is shown via pre-rendered layer above, just add styling */}
          {!isAnimating && !isTransitioning && currentCharIndex === targetCharIndex && (
            <>
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
            </>
          )}
        </div>
      </>
    );
  },
  (prevProps, nextProps) => {
    return (
      tokensEqual(prevProps.token, nextProps.token) &&
      prevProps.size === nextProps.size &&
      prevProps.boardType === nextProps.boardType &&
      prevProps.isAnimating === nextProps.isAnimating &&
      prevProps.animationsEnabled === nextProps.animationsEnabled
    );
  },
);

interface BoardDisplayProps {
  message: string | null;
  isLoading?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  boardType?: "black" | "white";
  deviceType?: DeviceType;
  /** Skip animation infrastructure and render plain divs per tile. Much
   *  cheaper for static previews that never animate. */
  isStatic?: boolean;
  /** Notes wide (for note_array device; ignored otherwise). */
  notesWide?: number;
  /** Notes tall (for note_array device; ignored otherwise). */
  notesTall?: number;
}

// Backward compatibility alias
type _FiestaboardDisplayProps = BoardDisplayProps;

export const BoardDisplay = memo(
  function BoardDisplay({
    message,
    isLoading = false,
    size = "md",
    className = "",
    boardType = "black",
    deviceType = "flagship",
    isStatic = false,
    notesWide = 1,
    notesTall = 1,
  }: BoardDisplayProps) {
    const t = useTranslations("boardDisplay");
    const animationsEnabled = useBoardAnimationsEnabled();
    // Get dimensions for the device type
    const dims = resolveDimensions(deviceType, notesWide, notesTall);
    const showSeams = isNoteArray(deviceType);
    // Seam gap: additional left/top margin applied at Note physical boundaries
    const seamGap = size === "sm" ? "6px" : size === "md" ? "8px" : "10px";

    // Memoize grid calculation to avoid recalculating on every render
    const grid = useMemo(() => {
      const messageForGrid = message ?? "";
      return messageToGrid(messageForGrid, dims.rows, dims.cols, deviceType);
    }, [message, dims.rows, dims.cols, deviceType]);

    // Increased padding for more pronounced bezel - more vertical space to match real board
    const paddingClasses = {
      sm: "px-3 py-4", // Small previews stay fixed size
      md: "px-2 py-3 sm:px-4 sm:py-6 md:px-5 md:py-8 lg:px-6 lg:py-10", // Responsive
      lg: "px-3 py-4 sm:px-5 sm:py-7 md:px-6 md:py-9 lg:px-8 lg:py-12", // Responsive
    };

    // Increased gap for more visible borders between tiles
    const gapClasses = {
      sm: "gap-[3px]", // Small previews stay fixed size
      md: "gap-[2px] sm:gap-[4px] md:gap-[5px]", // Responsive
      lg: "gap-[3px] sm:gap-[5px] md:gap-[6px] lg:gap-[7px]", // Responsive
    };

    // White board has light bezel and border
    const isWhiteBoard = boardType === "white";
    const bezelBg = isWhiteBoard ? "var(--color-board-bezel-light)" : "var(--color-board-bezel-dark)";
    const borderColor = isWhiteBoard ? "var(--color-board-bezel-border-light)" : "var(--color-board-bezel-border-dark)";

    // Enhanced shadow for depth
    const boxShadow = isWhiteBoard
      ? `
      0 8px 32px rgba(0,0,0,0.12),
      0 4px 16px rgba(0,0,0,0.08),
      inset 0 1px 2px rgba(255,255,255,0.9),
      inset 0 0 0 1px rgba(255,255,255,0.5)
    `
      : `
      0 8px 32px rgba(0,0,0,0.6),
      0 4px 16px rgba(0,0,0,0.4),
      inset 0 1px 1px rgba(255,255,255,0.08),
      inset 0 0 0 1px rgba(255,255,255,0.03)
    `;

    // Width is determined entirely by tile CSS classes × col count; no fixed minimum.

    // Adjust border and corner styles based on size
    const borderClasses =
      size === "sm"
        ? "rounded-lg border-[3px]" // Small previews stay fixed
        : "rounded-lg sm:rounded-xl border-[3px] sm:border-[4px] lg:border-[5px]"; // md/lg are responsive

    const boardText = useMemo(() => {
      if (isLoading) return t("loading");
      if (!message) return t("empty");
      return t("withMessage", {
        message: message
          .replace(/\{[^}]*\}/g, "")
          .replace(/\n/g, " ")
          .trim(),
      });
    }, [message, isLoading, t]);

    return (
      <div className={`w-full flex justify-center`}>
        <div
          role="img"
          aria-label={boardText}
          data-board-preview=""
          className={`${borderClasses} ${className} max-w-full`}
          style={{
            backgroundColor: bezelBg,
            borderColor,
            boxShadow,
            width: "fit-content",
          }}
        >
          {/* Inner bezel border */}
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
              {grid.map((row, rowIdx) => {
                const isRowSeam = showSeams && rowIdx > 0 && rowIdx % NOTE_ROWS === 0;
                return isStatic ? (
                  <StaticGridRow
                    key={`row-${rowIdx}`}
                    row={row}
                    rowIdx={rowIdx}
                    size={size}
                    gapClass={gapClasses[size]}
                    boardType={boardType}
                    showSeams={showSeams}
                    isRowSeam={isRowSeam}
                    seamGap={seamGap}
                  />
                ) : (
                  <GridRow
                    key={`row-${rowIdx}`}
                    row={row}
                    rowIdx={rowIdx}
                    size={size}
                    gapClass={gapClasses[size]}
                    boardType={boardType}
                    isAnimating={isLoading}
                    animationsEnabled={animationsEnabled}
                    showSeams={showSeams}
                    isRowSeam={isRowSeam}
                    seamGap={seamGap}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </div>
    );
  },
  (prevProps, nextProps) => {
    return (
      prevProps.message === nextProps.message &&
      prevProps.isLoading === nextProps.isLoading &&
      prevProps.size === nextProps.size &&
      prevProps.className === nextProps.className &&
      prevProps.boardType === nextProps.boardType &&
      prevProps.deviceType === nextProps.deviceType &&
      prevProps.notesWide === nextProps.notesWide &&
      prevProps.notesTall === nextProps.notesTall &&
      prevProps.isStatic === nextProps.isStatic
    );
  },
);

// Backward compatibility alias
export const FiestaboardDisplay = BoardDisplay;
