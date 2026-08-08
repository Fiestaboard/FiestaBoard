import { Box, Button, ScaledBoardDisplay, Text } from "@fiestaboard/ui";
import { Pause, Play } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import styles from "./styles.module.css";

/**
 * Animated multi-device hero board.
 *
 * Cycles through a mix of the Vestaboard hardware families FiestaBoard supports
 * - Flagship (22×6), Note (15×3), and Note Arrays in several sizes (wide 2×1,
 * tall 1×2, big 2×2) - showing data dashboards, colorful board art, and boards
 * that combine the two. Each one is captioned with what it is showing (`title`)
 * over what it is running on (`label`). For each board it:
 *   1. fades the previous board out,
 *   2. swaps to the new device (the grid-size change is hidden by the fade),
 *   3. fades the new board in while its contents flap in - every cell cycles
 *      through random values and settles on a staggered per-cell frame,
 *      left-to-right / top-to-bottom, like a real split-flap board. Character
 *      cells flap through glyphs; color tiles flap through colors.
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
  deviceType: "flagship" | "note" | "note_array";
  /** What the board is showing, e.g. "Market Movers". */
  title: string;
  /** What it is running on, e.g. "Flagship · 22 × 6". */
  label: string;
  message: string;
  notesWide?: number;
  notesTall?: number;
  /** Eligible to be the first board shown on load. See `pickOpener`. */
  opener?: boolean;
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

/**
 * The rotation, ordered so a text-heavy board never follows another one.
 * Color tiles (`{green}`) count as one cell each, so rows that mix tiles and
 * text still have to fit the device width: 22 cells on Flagship, 15 on Note.
 */
const BOARDS: BoardConfig[] = [
  {
    deviceType: "flagship",
    title: "Morning Dashboard",
    label: "Flagship · 22 × 6",
    message:
      "GOOD MORNING SF\n62F CLEAR   UV 4\nN JUDAH OB   4 MIN\nAAPL 232.10  +1.24%\nOCEAN BEACH 3-4 FT\nHAVE A GREAT DAY",
  },
  {
    deviceType: "flagship",
    title: "Market Movers",
    label: "Flagship · 22 × 6",
    opener: true,
    message:
      "MARKET MOVERS\n{green}AAPL  232.10  +1.24%\n{green}NVDA  121.44  +0.86%\n{red}TSLA  244.90  -2.10%\n{red}BTC   61,204  -1.40%\n{green}S+P   5,712   +0.42%",
  },
  {
    deviceType: "flagship",
    title: "Sunset Gradient",
    label: "Sun Art · 22 × 6",
    message: diagonalGradient(6, 22, SUNSET),
  },
  {
    deviceType: "flagship",
    title: "Weekly Forecast",
    label: "Flagship · 22 × 6",
    opener: true,
    message:
      "SF FORECAST\nMON {yellow} SUNNY     68 54\nTUE {blue} RAIN      61 52\nWED {violet} FOG       59 51\nTHU {yellow} SUNNY     70 55\nFRI {orange} HOT       78 58",
  },
  {
    deviceType: "note",
    title: "Daily Briefing",
    label: "Note · 15 × 3",
    message: "N JUDAH  4 MIN\nAAPL 232  +1.2%\n62F SUNNY   SF",
  },
  {
    deviceType: "note",
    title: "Game Day",
    label: "Note · 15 × 3",
    message: "{orange}SF 24  {red}LA 17\n4TH QTR   2:41\n{orange}SF BALL 1ST+10",
  },
  {
    deviceType: "note_array",
    notesWide: 2,
    notesTall: 1,
    title: "Transit + Markets",
    label: "Note Array · 2 × 1",
    // A 2 × 1 array is two 15-col Notes side by side, so each half is laid out
    // to its own 15 cells, with a blank column either side of the seam so the
    // two halves read as separate panels. (The rows this replaced were 31 cells
    // wide and lost their last character off the edge of the grid.)
    message: [
      "N JUDAH  4 MIN " + " BART    9 MIN",
      "AAPL 232 +1.2% " + " NVDA 121 -0.9%",
      "SURF OB 3-4 FT " + " UV INDEX    4",
    ].join("\n"),
  },
  {
    deviceType: "note_array",
    notesWide: 1,
    notesTall: 2,
    title: "Sunrise Column",
    label: "Note Array · 1 × 2 (tall)",
    message: verticalGradient(15, ["{yellow}", "{orange}", "{orange}", "{red}", "{violet}", "{blue}"]),
  },
  {
    deviceType: "note_array",
    notesWide: 2,
    notesTall: 2,
    title: "Rainbow Wash",
    label: "Note Array · 2 × 2",
    message: diagonalGradient(6, 30, RAINBOW),
  },
];

/**
 * Nine boards at ROTATE_MS each is a ~43s loop - longer than most visitors
 * stay - so start somewhere random rather than always on board 0. Openers are
 * limited to the full-size boards that show data and color at once, which is
 * the strongest first impression. Safe to randomize: this component only ever
 * renders in the browser (<BrowserOnly>), so there is no SSR markup to match.
 */
function pickOpener(): number {
  const openers = BOARDS.map((board, i) => (board.opener ? i : -1)).filter((i) => i >= 0);
  return openers[Math.floor(Math.random() * openers.length)];
}

const ROTATE_MS = 4800; // time each board is shown
const FADE_MS = 380; // fade-out before swapping devices
const FRAME_MS = 45; // scramble frame interval

/**
 * Split a row into board cells the way FiestaUI's renderer does: a `{color}`
 * token is one cell (a color tile), every other character is one cell. Lets a
 * single board mix data and color - `{green}AAPL 232.10` is one tile plus text.
 *
 * Closing tags (`{/red}`) render as zero cells and so would throw the cell
 * count off here; the boards above use bare color tiles only.
 */
function toCells(row: string): string[] {
  return row.match(/\{[^}]+\}|[\s\S]/g) ?? [];
}

/**
 * Run the split-flap scramble for a board, calling `onFrame` with each frame.
 * Cell (row r, col c) locks to its final value at frame
 * 4 + c*0.8 + r*1.6 + rand(0..7); until then it shows a random value of its own
 * kind - color tiles flap through colors, characters through glyphs. Returns
 * the interval id.
 */
function runScramble(board: BoardConfig, onFrame: (frame: string) => void): ReturnType<typeof setInterval> {
  const rows = board.message.split("\n").map(toCells);
  const settleAt = rows.map((cells, ri) => cells.map((_, ci) => 4 + ci * 0.8 + ri * 1.6 + Math.random() * 7));
  const randomCell = (cell: string) =>
    cell.startsWith("{")
      ? COLORS[Math.floor(Math.random() * COLORS.length)]
      : GLYPHS[Math.floor(Math.random() * GLYPHS.length)];

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
            return randomCell(cell);
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

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export default function HeroBoard(): ReactNode {
  const [shown, setShown] = useState(pickOpener);
  const [message, setMessage] = useState(() => BOARDS[shown].message);
  const [visible, setVisible] = useState(true);
  const [paused, setPaused] = useState(false);

  const shownRef = useRef(shown);
  const scrambleTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const fadeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cycleTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    shownRef.current = shown;
  }, [shown]);

  // The opening board flaps in on load.
  useEffect(() => {
    if (prefersReducedMotion()) return;
    scrambleTimer.current = runScramble(BOARDS[shownRef.current], setMessage);
    return () => clearInterval(scrambleTimer.current);
  }, []);

  // The rotation itself, torn down and rebuilt when the user pauses/resumes.
  useEffect(() => {
    if (paused) return;

    const reduceMotion = prefersReducedMotion();

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
        clearInterval(scrambleTimer.current);
        scrambleTimer.current = runScramble(BOARDS[next], setMessage); // flap the new contents in
      }, FADE_MS);
    }, ROTATE_MS);

    return () => {
      clearInterval(cycleTimer.current);
      // Pausing mid-fade would otherwise strand the board half-faded, since the
      // timeout that fades it back in never fires.
      clearTimeout(fadeTimer.current);
      setVisible(true);
    };
  }, [paused]);

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
      <Button
        variant="ghost"
        size="icon-sm"
        className={styles.pauseButton}
        onClick={() => setPaused((p) => !p)}
        aria-label={paused ? "Resume board rotation" : "Pause board rotation"}
      >
        {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
      </Button>
    </Box>
  );
}
