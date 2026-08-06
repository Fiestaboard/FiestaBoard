import { Box, ScaledBoardDisplay, Text } from "@fiestaboard/ui";
import { type ReactNode, useEffect, useRef, useState } from "react";

import styles from "./styles.module.css";

/**
 * Animated multi-device hero board.
 *
 * Cycles through a mix of the Vestaboard hardware families FiestaBoard supports
 * - Flagship (22×6), Note (15×3), and Note Arrays in several sizes (wide 2×1,
 * tall 1×2, big 2×2) - showing both data dashboards and colorful board art. For
 * each one it:
 *   1. fades the previous board out,
 *   2. swaps to the new device (the grid-size change is hidden by the fade),
 *   3. fades the new board in while its contents flap in - every cell cycles
 *      through random values and settles on a staggered per-cell frame,
 *      left-to-right / top-to-bottom, like a real split-flap board. Text boards
 *      flap through glyphs; art boards flap through colors.
 *
 * The flap is driven here (not FiestaUI's native board animation, which is
 * wired to the loading state) so it fires reliably on load and every cycle.
 * `ScaledBoardDisplay` fit-scales every device uniformly so nothing is
 * distorted, and we disable its own animation since we drive the frames.
 *
 * Rendered inside <BrowserOnly> (see src/pages/index.tsx). Respects
 * `prefers-reduced-motion`: no scramble, no fade - the message is set directly.
 */
type BoardConfig = {
  kind: "text" | "art";
  deviceType: "flagship" | "note" | "note_array";
  label: string;
  message: string;
  notesWide?: number;
  notesTall?: number;
};

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-:%";
const COLORS = ["{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}"];
const SUNSET = ["{yellow}", "{orange}", "{red}", "{violet}", "{blue}"];
const RAINBOW = ["{red}", "{orange}", "{yellow}", "{green}", "{blue}", "{violet}"];

/** A block of `cols` color tiles per row, one row per entry in `rowColors`. */
function verticalGradient(cols: number, rowColors: string[]): string {
  return rowColors.map((color) => color.repeat(cols)).join("\n");
}

/** A diagonal gradient across `palette`, blended from top-left to bottom-right. */
function diagonalGradient(rows: number, cols: number, palette: string[]): string {
  const lines: string[] = [];
  for (let r = 0; r < rows; r++) {
    let line = "";
    for (let c = 0; c < cols; c++) {
      const t = (r / Math.max(1, rows - 1) + c / Math.max(1, cols - 1)) / 2;
      line += palette[Math.min(palette.length - 1, Math.round(t * (palette.length - 1)))];
    }
    lines.push(line);
  }
  return lines.join("\n");
}

const BOARDS: BoardConfig[] = [
  {
    kind: "text",
    deviceType: "flagship",
    label: "Flagship · 22 × 6",
    message:
      "GOOD MORNING SF\n62F CLEAR   UV 4\nN JUDAH OB   4 MIN\nAAPL 232.10  +1.24%\nOCEAN BEACH 3-4 FT\nHAVE A GREAT DAY",
  },
  {
    kind: "art",
    deviceType: "flagship",
    label: "Sun Art · 22 × 6",
    message: diagonalGradient(6, 22, SUNSET),
  },
  {
    kind: "text",
    deviceType: "note",
    label: "Note · 15 × 3",
    message: "N JUDAH  4 MIN\nAAPL 232  +1.2%\n62F SUNNY   SF",
  },
  {
    kind: "text",
    deviceType: "note_array",
    notesWide: 2,
    notesTall: 1,
    label: "Note Array · 2 × 1",
    message: "MUNI N JUDAH 4MIN   BART  9 MIN\nAAPL 232 +1.2%   NVDA 121 -0.9%\nOCEAN BEACH 3-4FT   UV INDEX 4",
  },
  {
    kind: "art",
    deviceType: "note_array",
    notesWide: 1,
    notesTall: 2,
    label: "Note Array · 1 × 2 (tall)",
    message: verticalGradient(15, ["{yellow}", "{orange}", "{orange}", "{red}", "{violet}", "{blue}"]),
  },
  {
    kind: "art",
    deviceType: "note_array",
    notesWide: 2,
    notesTall: 2,
    label: "Note Array · 2 × 2",
    message: diagonalGradient(6, 30, RAINBOW),
  },
];

const ROTATE_MS = 4800; // time each board is shown
const FADE_MS = 380; // fade-out before swapping devices
const FRAME_MS = 45; // scramble frame interval

/**
 * Run the split-flap scramble for a board, calling `onFrame` with each frame.
 * Cell (row r, col c) locks to its final value at frame
 * 4 + c*0.8 + r*1.6 + rand(0..7); until then it shows a random value - a glyph
 * for text boards, a color tile for art boards. Returns the interval id.
 */
function runScramble(board: BoardConfig, onFrame: (frame: string) => void): ReturnType<typeof setInterval> {
  const art = board.kind === "art";
  // Split each row into cells: color tokens (`{red}`) for art, characters for text.
  const rows = board.message.split("\n").map((row) => (art ? (row.match(/\{[^}]+\}/g) ?? []) : Array.from(row)));
  const settleAt = rows.map((cells, ri) => cells.map((_, ci) => 4 + ci * 0.8 + ri * 1.6 + Math.random() * 7));
  const randomCell = () =>
    art ? COLORS[Math.floor(Math.random() * COLORS.length)] : GLYPHS[Math.floor(Math.random() * GLYPHS.length)];

  let frame = 0;
  const render = () => {
    frame += 1;
    let done = true;
    const out = rows
      .map((cells, ri) =>
        cells
          .map((cell, ci) => {
            if (frame >= settleAt[ri][ci]) return cell;
            done = false;
            return randomCell();
          })
          .join(""),
      )
      .join("\n");
    onFrame(out);
    if (done) {
      clearInterval(interval);
      onFrame(board.message);
    }
  };
  render(); // first scrambled frame immediately, so nothing pops in
  const interval = setInterval(render, FRAME_MS);
  return interval;
}

export default function HeroBoard(): ReactNode {
  const [shown, setShown] = useState(0);
  const [message, setMessage] = useState(BOARDS[0].message);
  const [visible, setVisible] = useState(true);

  const shownRef = useRef(0);
  const scrambleTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const fadeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cycleTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    shownRef.current = shown;
  }, [shown]);

  useEffect(() => {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    const flapIn = (n: number) => {
      clearInterval(scrambleTimer.current);
      if (reduceMotion) {
        setMessage(BOARDS[n].message);
        return;
      }
      scrambleTimer.current = runScramble(BOARDS[n], setMessage);
    };

    // First board flaps in on load.
    flapIn(0);

    cycleTimer.current = setInterval(() => {
      const next = (shownRef.current + 1) % BOARDS.length;
      if (reduceMotion) {
        setShown(next);
        setMessage(BOARDS[next].message);
        return;
      }
      setVisible(false); // fade current out
      clearTimeout(fadeTimer.current);
      fadeTimer.current = setTimeout(() => {
        setShown(next); // swap device (hidden by the fade)
        setVisible(true); // fade the new one in
        flapIn(next); // flap the new contents in
      }, FADE_MS);
    }, ROTATE_MS);

    return () => {
      clearInterval(scrambleTimer.current);
      clearInterval(cycleTimer.current);
      clearTimeout(fadeTimer.current);
    };
  }, []);

  const board = BOARDS[shown];

  return (
    <Box className={styles.stage}>
      <Box className={styles.frame} data-visible={visible}>
        <ScaledBoardDisplay
          key={shown}
          message={message}
          deviceType={board.deviceType}
          notesWide={board.notesWide}
          notesTall={board.notesTall}
          size="md"
          animationsEnabled={false}
        />
      </Box>
      <Text as="span" className={styles.caption} data-visible={visible}>
        {board.label}
      </Text>
    </Box>
  );
}
