import { StaticBoardDisplay } from "@fiestaboard/ui";
import { type ReactNode, useEffect, useRef, useState } from "react";

/**
 * Animated split-flap hero board.
 *
 * Cycles through three messages every 7s. On each change every character
 * scrambles through random glyphs and locks to its final value on a staggered
 * per-cell frame, producing a left-to-right / top-to-bottom flap-in (~1.5s).
 * Ported from FiestaboardSite.dc.html. Respects `prefers-reduced-motion` by
 * swapping the message directly with no scramble.
 *
 * Rendered inside <BrowserOnly> (see src/pages/index.tsx) — the split-flap
 * board and its timers are client-only.
 */
const HERO_MESSAGES = [
  "FIESTABOARD\n\nTURN YOUR SPLIT-FLAP\nDISPLAY INTO A LIVING\nDASHBOARD",
  "MUNI N JUDAH   4 MIN\nBART EMBARCADERO 9 M\n\nAAPL 232.10   +1.24%\nOCEAN BEACH 3-4FT AM",
  "26 PLUGINS\nWEATHER STOCKS SPORT\nTRANSIT SURF DISNEY\n\nRUNS IN DOCKER OR PI",
];
const SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-:%";

export default function HeroBoard(): ReactNode {
  const [display, setDisplay] = useState(HERO_MESSAGES[0]);
  const indexRef = useRef(0);
  const flipRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const cycleRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    const flipTo = (target: string) => {
      if (reduceMotion) {
        setDisplay(target);
        return;
      }
      clearInterval(flipRef.current);
      const rows = target.split("\n");
      const settleAt = rows.map((row, ri) =>
        Array.from(row).map((_, ci) => 4 + ci * 0.8 + ri * 1.6 + Math.random() * 7),
      );
      let frame = 0;
      flipRef.current = setInterval(() => {
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
        setDisplay(out);
        if (done) {
          clearInterval(flipRef.current);
          setDisplay(target);
        }
      }, 45);
    };

    cycleRef.current = setInterval(() => {
      indexRef.current = (indexRef.current + 1) % HERO_MESSAGES.length;
      flipTo(HERO_MESSAGES[indexRef.current]);
    }, 7000);

    return () => {
      clearInterval(flipRef.current);
      clearInterval(cycleRef.current);
    };
  }, []);

  return <StaticBoardDisplay message={display} size="md" />;
}
