import { ScaledBoardDisplay } from "@fiestaboard/ui";
import { type ReactNode, useEffect, useRef, useState } from "react";

import styles from "./styles.module.css";

/**
 * Animated multi-device hero board.
 *
 * Cycles through the three Vestaboard hardware families FiestaBoard supports —
 * Flagship (22×6), Note (15×3), and a Note Array (2×1) — cross-fading between
 * them and flapping each message in with the design system's native board
 * animation. `ScaledBoardDisplay` fit-scales each device uniformly, so nothing
 * is distorted (the previous single Flagship was squished by the column width).
 *
 * Rendered inside <BrowserOnly> (see src/pages/index.tsx). Respects
 * `prefers-reduced-motion` by disabling the flap and cross-fade.
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
      "GOOD MORNING SF\n62F CLEAR   UV 4\nN JUDAH OB   4 MIN\nAAPL 232.10 {green}+1.24%{/green}\nOCEAN BEACH 3-4 FT\nHAVE A GREAT DAY",
  },
  {
    deviceType: "note",
    label: "Note · 15 × 3",
    message: "N JUDAH  4 MIN\nAAPL 232 {green}+1.2%{/green}\n62F SUNNY   SF",
  },
  {
    deviceType: "note_array",
    label: "Note Array · 2 × 1",
    notesWide: 2,
    notesTall: 1,
    message:
      "MUNI N JUDAH 4MIN   BART  9 MIN\nAAPL 232 {green}+1.2%{/green}  NVDA 121 {red}-0.9%{/red}\nOCEAN BEACH 3-4FT   UV INDEX 4",
  },
];

const ROTATE_MS = 5000;

export default function HeroBoard(): ReactNode {
  const [index, setIndex] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const [animate, setAnimate] = useState(true);

  useEffect(() => {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    setAnimate(!reduceMotion);
    timer.current = setInterval(() => {
      setIndex((i) => (i + 1) % BOARDS.length);
    }, ROTATE_MS);
    return () => clearInterval(timer.current);
  }, []);

  const board = BOARDS[index];

  return (
    <div className={styles.stage}>
      {/* key remounts on change so the flap + fade-in replay for each device */}
      <div key={index} className={animate ? styles.frame : styles.frameStatic}>
        <ScaledBoardDisplay
          message={board.message}
          deviceType={board.deviceType}
          notesWide={board.notesWide}
          notesTall={board.notesTall}
          size="md"
          animationsEnabled={animate}
        />
      </div>
      <div className={styles.caption}>{board.label}</div>
    </div>
  );
}
