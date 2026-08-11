"use client";

import { Box, type FlapSpeed, resolveFlapSpeed, Text } from "@fiestaboard/ui";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useBoardAnimationsEnabled, useBoardFlapSpeed } from "@/hooks/use-board-animations";
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
// Shared loading ticker
//
// While `isLoading` is true every tile walks the character drum, which used to
// mean one `setInterval` per tile — ~132 timers for a Flagship, each firing its
// own `setState` and each drifting into its own phase. One timer per *period*
// instead: every subscriber still advances its own glyph from its own position,
// so the per-tile cycle is unchanged, but the tiles stay in phase with each
// other and React batches the whole board's updates into a single render pass.
//
// Keyed by period so two boards at different flap speeds do not share a clock.
// Ported from FiestaUI PR #202; the reduced-motion half of the upstream version
// is not needed here because Effect 1 short-circuits on `animationsEnabled`
// before it ever subscribes.
// ---------------------------------------------------------------------------

interface LoadingTicker {
  subscribers: Set<() => void>;
  intervalId: ReturnType<typeof setInterval> | null;
}

const loadingTickers = new Map<number, LoadingTicker>();

function subscribeLoadingTick(periodMs: number, callback: () => void): () => void {
  let ticker = loadingTickers.get(periodMs);
  if (!ticker) {
    ticker = { subscribers: new Set(), intervalId: null };
    loadingTickers.set(periodMs, ticker);
  }
  const entry = ticker;
  entry.subscribers.add(callback);
  if (entry.intervalId === null) {
    entry.intervalId = setInterval(() => {
      // Iterate a snapshot: a subscriber's setState cannot mutate the set
      // mid-loop, but this stays correct if that ever changes.
      for (const cb of [...entry.subscribers]) cb();
    }, periodMs);
  }
  return () => {
    entry.subscribers.delete(callback);
    if (entry.subscribers.size === 0) {
      if (entry.intervalId !== null) clearInterval(entry.intervalId);
      entry.intervalId = null;
      loadingTickers.delete(periodMs);
    }
  };
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
    <Box className={`absolute top-1/2 left-0 right-0 h-[1px] ${isWhiteBoard ? "bg-black/10" : "bg-black/30"}`} />
  );

  if (token.type === "color") {
    const bgColor = resolveColorCode(token.code, isWhiteBoard);
    const inset = size === "sm" ? "3px 1px 4px" : size === "md" ? "4px 2px 5px" : "5px 2px 6px";
    return (
      <Box className={`${sizeClass} relative rounded-[3px] overflow-hidden`} style={{ backgroundColor: tileBg }}>
        <Box className="absolute rounded-[2px]" style={{ inset, backgroundColor: bgColor }} />
        {splitLine}
      </Box>
    );
  }

  const displayChar = EXTRA_CHARS[token.value] ? token.value : BOARD_CHARS[getCharIndex(token.value)];
  const isBlank = displayChar === " ";

  return (
    <Box
      className={`${sizeClass} relative rounded-[3px] overflow-hidden flex items-center justify-center`}
      style={{ backgroundColor: tileBg }}
    >
      {!isBlank && (
        <Text
          as="span"
          className={`${textSizeClass} font-mono font-semibold select-none leading-none`}
          style={{ color: token.value === "♥" ? "#eb4034" : textColor }}
        >
          {displayChar}
        </Text>
      )}
      {splitLine}
    </Box>
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
  emitCellMetadata = false,
}: {
  row: Token[];
  rowIdx: number;
  size: "sm" | "md" | "lg";
  gapClass: string;
  boardType: "black" | "white";
  showSeams?: boolean;
  isRowSeam?: boolean;
  seamGap?: string;
  emitCellMetadata?: boolean;
}) {
  return (
    <Box
      data-note-row=""
      {...(isRowSeam ? { "data-note-row-seam": "true" } : {})}
      className={`flex ${gapClass} justify-center`}
      style={isRowSeam ? { marginTop: seamGap } : undefined}
    >
      {row.map((token, colIdx) => {
        const isColSeam = showSeams && colIdx > 0 && colIdx % NOTE_COLS === 0;
        // Mirror the animated path's wrapper for DOM consistency; hosts the
        // data-note-tile hook + note-array seam margin. Draw-mode cell
        // metadata (coordinates + cell value) is opt-in — see
        // BoardDisplayProps.emitCellMetadata.
        return (
          <Box
            key={`col-${rowIdx}-${colIdx}`}
            data-note-tile=""
            {...(emitCellMetadata
              ? { "data-row": rowIdx, "data-col": colIdx, "data-cell-value": getCharFromToken(token) }
              : {})}
            {...(isColSeam ? { "data-note-col-seam": "true" } : {})}
            style={isColSeam ? { marginLeft: seamGap } : undefined}
          >
            <StaticTile token={token} size={size} boardType={boardType} />
          </Box>
        );
      })}
    </Box>
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
    flapStepMs,
    showSeams = false,
    isRowSeam = false,
    seamGap = "6px",
    emitCellMetadata = false,
  }: {
    row: Token[];
    rowIdx: number;
    size: "sm" | "md" | "lg";
    gapClass: string;
    boardType?: "black" | "white";
    isAnimating?: boolean;
    animationsEnabled?: boolean;
    /** Resolved milliseconds per character step — see the `flapSpeed` prop. */
    flapStepMs: number;
    showSeams?: boolean;
    isRowSeam?: boolean;
    seamGap?: string;
    emitCellMetadata?: boolean;
  }) {
    return (
      <Box
        data-note-row=""
        {...(isRowSeam ? { "data-note-row-seam": "true" } : {})}
        className={`flex ${gapClass} justify-center`}
        style={isRowSeam ? { marginTop: seamGap } : undefined}
      >
        {row.map((token, colIdx) => {
          const isColSeam = showSeams && colIdx > 0 && colIdx % NOTE_COLS === 0;
          // The wrapper is structurally required: CharTile returns a fragment
          // (flap-animation layers), so it needs a single containing flex item.
          // It also hosts the data-note-tile hook + note-array seam margin.
          // Draw-mode cell coordinates are opt-in — see
          // BoardDisplayProps.emitCellMetadata.
          return (
            <Box
              key={`col-${rowIdx}-${colIdx}`}
              data-note-tile=""
              {...(emitCellMetadata ? { "data-row": rowIdx, "data-col": colIdx } : {})}
              {...(isColSeam ? { "data-note-col-seam": "true" } : {})}
              style={isColSeam ? { marginLeft: seamGap } : undefined}
            >
              <CharTile
                token={token}
                size={size}
                boardType={boardType}
                isAnimating={isAnimating}
                animationsEnabled={animationsEnabled}
                flapStepMs={flapStepMs}
                rowIdx={rowIdx}
                colIdx={colIdx}
              />
            </Box>
          );
        })}
      </Box>
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
    if (prevProps.flapStepMs !== nextProps.flapStepMs) return false;
    if (prevProps.showSeams !== nextProps.showSeams) return false;
    if (prevProps.isRowSeam !== nextProps.isRowSeam) return false;
    if (prevProps.seamGap !== nextProps.seamGap) return false;
    if (prevProps.emitCellMetadata !== nextProps.emitCellMetadata) return false;

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
    flapStepMs,
    rowIdx = 0,
    colIdx = 0,
  }: {
    token: Token;
    size?: "sm" | "md" | "lg";
    boardType?: "black" | "white";
    isAnimating?: boolean;
    animationsEnabled?: boolean;
    /** Resolved milliseconds per character step — see the `flapSpeed` prop. */
    flapStepMs: number;
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

    // All tiles flip in sync — same duration, no random delay. This one number
    // drives the character stepper, the loading ticker and both leaf
    // animations, so no two of them can drift apart. It comes from the
    // `flapSpeed` prop / the user's board-speed setting; see `FLAP_SPEED_PRESETS`
    // in `@fiestaboard/ui`, which this board deliberately borrows rather than
    // re-declaring a parallel preset vocabulary.
    const animationDuration = flapStepMs;

    // ── Tile state, and the refs that mirror it ────────────────────────────
    //
    // Both effects below run inside the same passive-effect flush and both can
    // read (and write) the tile's position, so neither may rely on a value that
    // only becomes visible after the *next* commit. Every write therefore goes
    // through `setCurrentChar` / `setTransitioning`, which update the ref and
    // the state together. Previously the ref was synced from a *third*
    // `useEffect` that ran a commit later, so an effect could read a position
    // another effect had already invalidated — see the note on Effect 1's
    // dependencies. Ported from FiestaUI PR #202 (issue #196).
    //
    // Always start from the target character: tiles are set by the parent, and
    // rotate only while loading or while stepping to a new target.
    const [currentCharIndex, setCurrentCharIndexState] = useState(() => targetCharIndex);
    const [isTransitioning, setIsTransitioningState] = useState(false);

    const currentCharIndexRef = useRef(currentCharIndex);
    const isTransitioningRef = useRef(false);
    const prevTargetCharIndexRef = useRef(targetCharIndex);
    const prevIsAnimatingRef = useRef(isAnimating);
    const justStoppedLoadingRef = useRef(false);

    // The live target, readable synchronously. Effect 1 needs it (a message can
    // change in the same commit that loading stops) but must NOT re-run on it —
    // see its dependency list. Declared above Effect 1 so it is already fresh
    // when Effect 1 runs in the same flush.
    const targetCharIndexRef = useRef(targetCharIndex);
    useEffect(() => {
      targetCharIndexRef.current = targetCharIndex;
    }, [targetCharIndex]);

    const setCurrentChar = useCallback((index: number) => {
      currentCharIndexRef.current = index;
      setCurrentCharIndexState(index);
    }, []);

    const setTransitioning = useCallback((next: boolean) => {
      isTransitioningRef.current = next;
      setIsTransitioningState(next);
    }, []);

    // ── The character stepper ──────────────────────────────────────────────
    //
    // One owner for the timer that walks a tile around the character drum. It
    // is held in a ref and torn down on unmount (or when a branch below decides
    // the tile has arrived) — deliberately *not* from an effect's cleanup.
    // Effect 2 re-runs whenever the target changes, and a cleanup there would
    // clear the very interval that same effect had just started as soon as a
    // second message arrived mid-cascade, stranding the tile with
    // `isTransitioning` stuck true and nothing left to advance it.
    const stepIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const stepPeriodRef = useRef(0);

    const stopStepping = useCallback(() => {
      if (stepIntervalRef.current !== null) {
        clearInterval(stepIntervalRef.current);
        stepIntervalRef.current = null;
      }
    }, []);

    // Advance one character toward whatever `prevTargetCharIndexRef` currently
    // holds, so a target that changes mid-cascade is picked up on the next step
    // instead of restarting the walk. Reading and writing the position through
    // the ref (rather than a `setCurrentCharIndex` updater) keeps the decision
    // and the write in the same tick: an updater is evaluated later, against
    // whatever else has been queued in the meantime, which is precisely how the
    // cascade used to cancel itself.
    const step = useCallback(() => {
      const target = prevTargetCharIndexRef.current;
      const current = currentCharIndexRef.current;
      const arrive = () => {
        stopStepping();
        setTransitioning(false);
        justStoppedLoadingRef.current = false;
      };
      if (current === target) {
        arrive();
        return;
      }
      const next = (current + 1) % BOARD_CHARS.length;
      setCurrentChar(next);
      if (next === target) arrive();
    }, [setCurrentChar, setTransitioning, stopStepping]);

    // Idempotent for an unchanged period, so retargeting mid-cascade keeps the
    // existing timer (and its phase) instead of resetting the clock every time
    // a new message lands. A changed flap speed does restart it, at the new
    // cadence.
    const startStepping = useCallback(
      (periodMs: number) => {
        if (stepIntervalRef.current !== null && stepPeriodRef.current === periodMs) return;
        stopStepping();
        stepPeriodRef.current = periodMs;
        stepIntervalRef.current = setInterval(step, periodMs);
      },
      [step, stopStepping],
    );

    // Unmount only — the stepper outlives individual effect runs by design.
    useEffect(() => stopStepping, [stopStepping]);

    // Effect 1: the loading lifecycle (the `isAnimating` prop), and nothing else.
    //
    // It does NOT depend on `targetCharIndex`. It used to, "so we can transition
    // to it when loading stops" — but that also re-ran the whole effect on every
    // *message* change, and its idle branch (bottom) then snapped
    // `currentCharIndex` straight to the new target. Effect 2 runs later in the
    // same flush, so by the time it tried to step the tile the position it was
    // supposed to step away from was already gone, and the cascade cancelled
    // itself on its very first step: a message change snapped and no flap layers
    // ever mounted. Same root cause as FiestaUI issue #196, same fix as its
    // PR #202.
    //
    // The value it actually needs — the live target at the moment loading stops,
    // which may have changed in the same commit — comes from
    // `targetCharIndexRef`, synced by an effect declared above this one and
    // therefore already fresh when this one runs.
    useEffect(() => {
      const wasAnimating = prevIsAnimatingRef.current;
      prevIsAnimatingRef.current = isAnimating;
      const target = targetCharIndexRef.current;

      // If animations are disabled (user setting or reduce-motion), short-circuit:
      // stop the stepper and snap to target without rotating.
      if (!animationsEnabled) {
        stopStepping();
        setTransitioning(false);
        setCurrentChar(target);
        prevTargetCharIndexRef.current = target;
        justStoppedLoadingRef.current = false;
        return;
      }

      if (isAnimating) {
        // Loading state: cycle through all characters continuously. Don't reset
        // to target — just continue from the current position, unless loading
        // has only just started.
        setTransitioning(false);
        stopStepping();

        if (!wasAnimating) setCurrentChar(target);

        // One timer for every loading tile at this cadence, rather than ~132
        // per board — see `subscribeLoadingTick`.
        return subscribeLoadingTick(animationDuration, () => {
          setCurrentChar((currentCharIndexRef.current + 1) % BOARD_CHARS.length);
        });
      }

      if (wasAnimating) {
        // Just stopped loading — walk from wherever the drum stopped to the
        // target. Mark it so Effect 2 hands this transition over rather than
        // starting a competing one.
        justStoppedLoadingRef.current = true;
        stopStepping();

        const prevTarget = prevTargetCharIndexRef.current;
        prevTargetCharIndexRef.current = target;

        // Already there, or the target never changed while loading: only tiles
        // whose character actually changed are supposed to flip.
        if (currentCharIndexRef.current === target || prevTarget === target) {
          setTransitioning(false);
          setCurrentChar(target);
          justStoppedLoadingRef.current = false;
          return;
        }

        setTransitioning(true);
        step(); // first flap immediately, then one per interval
        if (isTransitioningRef.current) startStepping(animationDuration);
        return;
      }

      // Idle, and idle before: nothing for the loading lifecycle to do. A
      // *target* change is Effect 2's business — reacting to it here is what
      // broke the cascade. The one thing worth asserting is that a tile which
      // is neither loading nor stepping sits on its target (e.g. after the flap
      // speed or `animationsEnabled` changed underneath it).
      if (!isTransitioningRef.current) {
        stopStepping();
        if (currentCharIndexRef.current !== target) setCurrentChar(target);
      }
    }, [
      isAnimating,
      animationDuration,
      animationsEnabled,
      setCurrentChar,
      setTransitioning,
      startStepping,
      step,
      stopStepping,
    ]);

    // Effect 2: message changes — the cascade.
    //
    // `isTransitioning` is deliberately absent from the dependencies. It is
    // state this effect *sets*, so depending on it made the effect tear itself
    // down and re-enter its own "already transitioning, don't interfere" guard
    // one commit after starting a cascade. The guard reads
    // `isTransitioningRef` instead, which is written at the same instant as the
    // state, and the stepper is owned by refs rather than by this effect's
    // cleanup so a second message mid-cascade retargets the walk instead of
    // stranding it.
    useEffect(() => {
      // Animations disabled (the `board_animations` kill switch, `reduce_motion`,
      // or `prefers-reduced-motion: reduce` — `useBoardAnimationsEnabled`
      // collapses all three into this prop): snap directly to the target — no
      // flap, no rotation through intermediate characters. A message change is
      // not one animation but a cascade of up to ~70 consecutive flips, so the
      // CSS `prefers-reduced-motion` catch-all in globals.css cannot help: it
      // only truncates each individual flap and would leave the JS-driven glyph
      // cascade intact. Matches FiestaUI issue #180.
      if (!animationsEnabled) {
        prevTargetCharIndexRef.current = targetCharIndex;
        stopStepping();
        setTransitioning(false);
        setCurrentChar(targetCharIndex);
        return;
      }

      // Loading, or walking out of loading: Effect 1 owns the tile. Publish the
      // new target so the walk in flight retargets, and stay out of the way.
      if (isAnimating || justStoppedLoadingRef.current) {
        prevTargetCharIndexRef.current = targetCharIndex;
        return;
      }

      // A cascade is already in flight — retarget it in place. `step` re-reads
      // the target every tick, so the tile continues from where it is toward
      // the new character rather than restarting.
      if (isTransitioningRef.current) {
        prevTargetCharIndexRef.current = targetCharIndex;
        startStepping(animationDuration);
        return;
      }

      const prevTarget = prevTargetCharIndexRef.current;
      prevTargetCharIndexRef.current = targetCharIndex;

      // Target unchanged, or the tile is already showing it: only tiles whose
      // character actually changed are supposed to flip.
      if (prevTarget === targetCharIndex || currentCharIndexRef.current === targetCharIndex) {
        stopStepping();
        setTransitioning(false);
        if (currentCharIndexRef.current !== targetCharIndex) setCurrentChar(targetCharIndex);
        return;
      }

      setTransitioning(true);
      step(); // first flap immediately, then one per interval
      if (isTransitioningRef.current) startStepping(animationDuration);
    }, [
      targetCharIndex,
      isAnimating,
      animationDuration,
      animationsEnabled,
      setCurrentChar,
      setTransitioning,
      startStepping,
      step,
      stopStepping,
    ]);

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
        <Box
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
                  <Box
                    key={`static-color-${token.code}`}
                    className={`absolute inset-0 ${marginClasses} flex items-center justify-center`}
                    style={{ zIndex: 2 }}
                  >
                    <Box
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
                      <Box className="absolute top-1/2 left-0 right-0 h-[1px] bg-black/10" />
                    </Box>
                  </Box>
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
                <Box
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
                    <Text
                      as="span"
                      className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none relative z-10`}
                      style={{ color: charColor }}
                    >
                      {targetChar}
                    </Text>
                  )}
                  {/* Blank/space character - render as empty but maintain layout */}
                  {!isColor && targetChar === " " && (
                    <Text
                      as="span"
                      className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none relative z-10`}
                      style={{ color: textColor, visibility: "hidden" }}
                      aria-hidden="true"
                    >
                      {" "}
                    </Text>
                  )}
                  {isColor && (
                    <Box
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
                </Box>
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
                  <Box
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
                      <Text
                        as="span"
                        className={`${textSizeClasses[size]} font-mono font-semibold select-none leading-none`}
                        style={{ color: isHeart ? "#eb4034" : textColor }}
                      >
                        {char}
                      </Text>
                    )}
                  </Box>
                );
              };

              return (
                <>
                  {/* Layer 1: new char top half — sits behind falling top flap */}
                  <Box
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
                  </Box>

                  {/* Layer 2: old char bottom half — sits behind unfolding bottom flap */}
                  <Box
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
                  </Box>

                  {/* Layer 3: top flap — old char top half, folds DOWN (hinged at midpoint) */}
                  <Box
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
                    <Box
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
                  </Box>

                  {/* Layer 4: bottom flap — new char bottom half, UNFOLDS into place */}
                  <Box
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
                    <Box
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
                  </Box>

                  {/* Shadow cast by falling flap onto bottom half */}
                  <Box
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
                  <Box
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
              <Box
                className={`absolute top-1/2 left-0 right-0 h-[1px] ${isWhiteBoard ? "bg-black/10" : "bg-black/30"}`}
                style={{ zIndex: 3 }}
              />
              <Box
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
        </Box>
      </>
    );
  },
  (prevProps, nextProps) => {
    return (
      tokensEqual(prevProps.token, nextProps.token) &&
      prevProps.size === nextProps.size &&
      prevProps.boardType === nextProps.boardType &&
      prevProps.isAnimating === nextProps.isAnimating &&
      prevProps.animationsEnabled === nextProps.animationsEnabled &&
      prevProps.flapStepMs === nextProps.flapStepMs
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
  /** Emit data-row / data-col / data-cell-value on every tile wrapper.
   *  Only the page editor's draw mode consumes these (DrawableBoardPreview
   *  hit-tests strokes via data-row/data-col and tests read data-cell-value),
   *  so they are off by default — computing per-tile metadata is wasted work
   *  for the many static previews (dashboards, lists, chat cards) that never
   *  draw, and stray data-row/data-col on unrelated previews would force the
   *  draw surface's hit-testing to reject them one by one. */
  emitCellMetadata?: boolean;
  /** How fast a tile advances one character: a named cadence (`"standard"` —
   *  the 80ms this board has always shipped — `"quick"`, `"relaxed"`, or the
   *  hardware's own `"hardware"`), or `{ durationMs }` for anything else,
   *  clamped to [8, 2000]. Drives the leaf animations and the loading cadence
   *  together.
   *
   *  Omit it and the board follows the user's `board_flap_speed` display
   *  setting, exactly as `animationsEnabled` follows `board_animations`. Pass
   *  it only to override that for a specific surface — the settings live
   *  preview does, so a user can compare cadences before committing to one.
   *
   *  The preset vocabulary is imported from `@fiestaboard/ui` rather than
   *  re-declared here, so the app and the package cannot drift on what
   *  `"quick"` means. */
  flapSpeed?: FlapSpeed;
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
    emitCellMetadata = false,
    flapSpeed,
  }: BoardDisplayProps) {
    const t = useTranslations("boardDisplay");
    const animationsEnabled = useBoardAnimationsEnabled();
    // One resolved number for both CSS leaf animations *and* the JS cadence —
    // the per-character stepper and the loading ticker both read it, so the
    // setting changes the whole step, not just the rotation. An explicit
    // `flapSpeed` prop wins over the stored setting (the settings preview).
    const settingFlapSpeed = useBoardFlapSpeed();
    const flapStepMs = resolveFlapSpeed(flapSpeed ?? settingFlapSpeed);
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
      <Box className={`w-full flex justify-center`}>
        <Box
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
          <Box
            className={`${paddingClasses[size]} relative`}
            aria-hidden="true"
            style={{
              background: isWhiteBoard
                ? "linear-gradient(135deg, var(--color-board-surface-light) 0%, var(--color-board-bezel-border-light) 100%)"
                : "linear-gradient(135deg, var(--color-board-surface-dark) 0%, var(--color-board-black) 100%)",
            }}
          >
            <Box className={`flex flex-col ${gapClasses[size]}`}>
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
                    emitCellMetadata={emitCellMetadata}
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
                    flapStepMs={flapStepMs}
                    showSeams={showSeams}
                    isRowSeam={isRowSeam}
                    seamGap={seamGap}
                    emitCellMetadata={emitCellMetadata}
                  />
                );
              })}
            </Box>
          </Box>
        </Box>
      </Box>
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
      prevProps.isStatic === nextProps.isStatic &&
      prevProps.emitCellMetadata === nextProps.emitCellMetadata &&
      // Compare the resolved step, not the prop: `{ durationMs: 80 }` written
      // inline is a new object every render but the same cadence, and
      // `"standard"` and `{ durationMs: 80 }` are the same board.
      resolveFlapSpeed(prevProps.flapSpeed ?? "standard") === resolveFlapSpeed(nextProps.flapSpeed ?? "standard")
    );
  },
);

// Backward compatibility alias
export const FiestaboardDisplay = BoardDisplay;
