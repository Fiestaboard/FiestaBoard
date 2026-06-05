"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { BoardDisplay } from "@/components/board-display";

type BoardProps = React.ComponentProps<typeof BoardDisplay>;

/**
 * Wraps {@link BoardDisplay} so it shrinks to fit a narrow parent.
 *
 * BoardDisplay sizes its tiles via viewport breakpoints
 * (`sm:w-[20px] md:w-[24px]…`). That works on a full-width page but
 * stops responding when the editor pane is squeezed by, say, the
 * resizable AI chat panel — the board overflows or gets clipped.
 *
 * Here we keep the natural tile rendering and just apply
 * `transform: scale()` based on the actual parent width measured at
 * runtime. We never scale UP — full size is always the cap, so the
 * board looks identical in roomy layouts.
 */
export function ScaledBoardDisplay(props: BoardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const boardRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [scaledWidth, setScaledWidth] = useState<number | null>(null);
  const [scaledHeight, setScaledHeight] = useState<number | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const board = boardRef.current;
    if (!container || !board) return;

    // Walk up to the closest ancestor that actually constrains width.
    // BoardDisplay renders with `width: fit-content`, so every plain
    // wrapper above it expands to the board's natural width too —
    // `container.clientWidth` would always equal the board width and
    // we'd never scale. We stop at the first ancestor whose computed
    // overflow-x is `hidden`, `scroll`, or `auto`, since that's where
    // the visible width is genuinely capped.
    const findConstraint = (): HTMLElement => {
      let el: HTMLElement | null = container.parentElement;
      while (el) {
        const cs = getComputedStyle(el);
        if (cs.overflowX === "hidden" || cs.overflowX === "scroll" || cs.overflowX === "auto") {
          return el;
        }
        el = el.parentElement;
      }
      return container;
    };

    let rafId: number | null = null;
    const compute = () => {
      rafId = null;
      const constraint = findConstraint();
      // The constraint's clientWidth excludes its own padding, which
      // is the visible content area we have to fit.
      const cw = constraint.clientWidth;
      // Board's natural (un-transformed) width — read offsetWidth on
      // the actual rendered board so the current transform doesn't
      // skew the measurement.
      const inner = board.firstElementChild as HTMLElement | null;
      const bw = inner ? inner.offsetWidth : board.offsetWidth;
      const bh = inner ? inner.offsetHeight : board.offsetHeight;
      if (!bw || !cw) return;
      const next = Math.min(1, cw / bw);
      setScale((prev) => (Math.abs(prev - next) > 0.001 ? next : prev));
      setScaledWidth(bw * next);
      setScaledHeight(bh * next);
    };
    // Coalesce ResizeObserver callbacks via rAF — the resize handle
    // can fire dozens of events per second while the user drags, and
    // BoardDisplay is heavy (one component per tile). One write per
    // frame is plenty.
    const recompute = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(compute);
    };

    compute();
    const ro = new ResizeObserver(recompute);
    ro.observe(findConstraint());
    ro.observe(board);
    return () => {
      ro.disconnect();
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [props.message, props.size, props.deviceType]);

  return (
    // Outer: full-width, centers the scaled board horizontally.
    //
    // Middle: a fixed-size box that matches the *post-scale* dimensions.
    // This keeps surrounding layout (e.g. preview margin, the live-output
    // toggle below) honest — without it, the BoardDisplay's natural
    // 779px-wide layout box would still take that much room and push
    // siblings around.
    //
    // Inner: the BoardDisplay itself, transformed from its top-left so
    // the visible content lines up with the middle box from x=0.
    <div ref={containerRef} className="flex w-full min-w-0 justify-center overflow-hidden">
      <div
        style={{
          width: scaledWidth ?? undefined,
          height: scaledHeight ?? undefined,
        }}
      >
        <div
          ref={boardRef}
          style={{
            transform: `scale(${scale})`,
            transformOrigin: "top left",
            width: "fit-content",
          }}
        >
          <BoardDisplay {...props} />
        </div>
      </div>
    </div>
  );
}
