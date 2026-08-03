import { ScaledBoardDisplay } from "@fiestaboard/ui";
import { type ReactNode, useEffect, useRef, useState } from "react";

import styles from "./styles.module.css";

/**
 * Animated multi-device hero board.
 *
 * Cycles through the three Vestaboard hardware families FiestaBoard supports —
 * Flagship (22×6), Note (15×3), and a Note Array (2×1) — and for each one:
 *   1. fades the previous board out,
 *   2. swaps to the new device (the grid-size change is hidden by the fade),
 *   3. fades the new board in while its message flaps in — every character
 *      scrambles through random glyphs and settles on a staggered per-cell
 *      frame, left-to-right / top-to-bottom, like a real split-flap board.
 *
 * The flap is driven here (not FiestaUI's native board animation, which is
 * wired to the loading state) so it fires reliably on load and every cycle.
 * `ScaledBoardDisplay` fit-scales every device uniformly so nothing is
 * distorted, and we disable its own animation since we drive the frames.
 *
 * Rendered inside <BrowserOnly> (see src/pages/index.tsx). Respects
 * `prefers-reduced-motion`: no scramble, no fade — the message is set directly.
 */
type BoardConfig = {
  deviceType: "flagship" | "note" | "note_array";
  label: string;
  message: string;
  notesWide?: number;
  notesTall?: number;
};

const BOARDS: BoardConfig[] = [
  {
    deviceType: "flagship",
    label: "Flagship · 22 × 6",
    message:
      "GOOD MORNING SF\n62F CLEAR   UV 4\nN JUDAH OB   4 MIN\nAAPL 232.10  +1.24%\nOCEAN BEACH 3-4 FT\nHAVE A GREAT DAY",
  },
  {
    deviceType: "note",
    label: "Note · 15 × 3",
    message: "N JUDAH  4 MIN\nAAPL 232  +1.2%\n62F SUNNY   SF",
  },
  {
    deviceType: "note_array",
    label: "Note Array · 2 × 1",
    notesWide: 2,
    notesTall: 1,
    message: "MUNI N JUDAH 4MIN   BART  9 MIN\nAAPL 232 +1.2%   NVDA 121 -0.9%\nOCEAN BEACH 3-4FT   UV INDEX 4",
  },
];

const SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-:%";
const ROTATE_MS = 5200; // time each board is shown
const FADE_MS = 380; // fade-out before swapping devices
const FRAME_MS = 45; // scramble frame interval

/**
 * Run the split-flap scramble for `target`, calling `onFrame` with each frame.
 * Character (row r, col c) locks to its final value at frame
 * 4 + c*0.8 + r*1.6 + rand(0..7); until then it shows a random glyph. Returns
 * the interval id so the caller can cancel it.
 */
function runScramble(target: string, onFrame: (frame: string) => void): ReturnType<typeof setInterval> {
  const rows = target.split("\n");
  const settleAt = rows.map((row, ri) => Array.from(row).map((_, ci) => 4 + ci * 0.8 + ri * 1.6 + Math.random() * 7));
  let frame = 0;
  const render = () => {
    frame += 1;
    let done = true;
    const out = rows
      .map((row, ri) =>
        Array.from(row)
          .map((char, ci) => {
            if (frame >= settleAt[ri][ci]) return char;
            done = false;
            return SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
          })
          .join(""),
      )
      .join("\n");
    onFrame(out);
    if (done) {
      clearInterval(interval);
      onFrame(target);
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
      scrambleTimer.current = runScramble(BOARDS[n].message, setMessage);
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
        flapIn(next); // scramble the new message in
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
    <div className={styles.stage}>
      <div className={styles.frame} data-visible={visible}>
        <ScaledBoardDisplay
          key={shown}
          message={message}
          deviceType={board.deviceType}
          notesWide={board.notesWide}
          notesTall={board.notesTall}
          size="md"
          animationsEnabled={false}
        />
      </div>
      <div className={styles.caption} data-visible={visible}>
        {board.label}
      </div>
    </div>
  );
}
