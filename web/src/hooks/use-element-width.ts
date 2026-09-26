"use client";

import { useLayoutEffect, useState } from "react";

/**
 * The measured width of an element, in CSS pixels.
 *
 * The drawer's chrome has to make layout DECISIONS, not just style itself:
 * a keyboard hint that becomes a tooltip, a mode control that moves to its
 * own row. A CSS container query can hide a box but cannot move a control
 * into a different parent or swap it for another affordance, so the panel
 * measures itself and decides in React.
 *
 * Measured in a layout effect before paint, so the first painted frame is
 * already the right layout — no flash of the wide arrangement on a phone.
 * `ResizeObserver` then keeps it honest through drawer width changes,
 * device rotation and window resizes.
 */
export function useElementWidth(ref: React.RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;

    const measure = () => setWidth(element.getBoundingClientRect().width);
    measure();

    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return width;
}
