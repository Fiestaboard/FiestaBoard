"use client";

import { useEffect, useId, useRef } from "react";

const KEY = "fbOverlay";

/**
 * Back closes an open sheet or dialog instead of leaving the screen
 * (BB-A-12, the Android convention for modal sheets).
 *
 * While `open`, one history entry is pushed for the overlay (same URL, the
 * router's own state kept). Back pops it, and the overlay closes. Closed any
 * other way (its X, the scrim, a submit), the entry is taken back so the
 * history is as it was. If the overlay closes because the app navigated
 * somewhere else, the entry is no longer on top and is left alone.
 */
export function useCloseOnBack(open: boolean, close: () => void): void {
  const id = useId();
  const closeRef = useRef(close);
  useEffect(() => {
    closeRef.current = close;
  }, [close]);
  useEffect(() => {
    if (!open || typeof window === "undefined") return;
    const state: unknown = window.history.state;
    window.history.pushState({ ...(state && typeof state === "object" ? state : {}), [KEY]: id }, "");
    let popped = false;
    const onPop = () => {
      popped = true;
      closeRef.current();
    };
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      const top: unknown = window.history.state;
      if (!popped && top && typeof top === "object" && (top as Record<string, unknown>)[KEY] === id) {
        window.history.back();
      }
    };
  }, [open, id]);
}
