"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  AI_DRAWER_DRAGGING_CLASS,
  AI_DRAWER_OPEN_CLASS,
  AI_DRAWER_WIDTH_VAR,
  clampDrawerWidth,
  DEFAULT_AI_DRAWER_WIDTH,
  maxDrawerWidth,
  MIN_AI_DRAWER_WIDTH,
  readStoredDrawerWidth,
  storeDrawerWidth,
} from "@/lib/ai-drawer-width";

/**
 * The drawer's width, and the page's knowledge of it.
 *
 * The width is published on `<html>` as a custom property rather than
 * threaded through React, because the element that has to react to it is
 * `MainContent`'s `<main>` — a sibling several levels up, rendered by the
 * design-system package, whose reservation used to be a hardcoded 396px.
 * A custom property lets the reservation follow the live width during a
 * drag without re-rendering the page under it (globals.css).
 */
export interface AiDrawerWidthControls {
  width: number;
  minWidth: number;
  /** The widest this viewport allows right now. */
  maxWidth: number;
  /** Request a width; clamped, applied, and remembered. */
  setWidth: (width: number) => void;
  /** Swap between the default width and the last custom one. */
  toggleWidth: () => void;
  /** Back to the default width. */
  resetWidth: () => void;
  /** Tell the page a drag is live, so it drops the width transition. */
  setDragging: (dragging: boolean) => void;
}

const viewportWidth = () => (typeof window === "undefined" ? 0 : window.innerWidth);

export function useAiDrawerWidth(isOpen: boolean): AiDrawerWidthControls {
  const [width, setWidthState] = useState(() => {
    const stored = readStoredDrawerWidth();
    return stored === null ? DEFAULT_AI_DRAWER_WIDTH : clampDrawerWidth(stored, viewportWidth());
  });
  const [maxWidth, setMaxWidth] = useState(() => maxDrawerWidth(viewportWidth()));
  // The width to come back to when the toggle leaves the default.
  const lastCustomRef = useRef<number | null>(null);

  const setWidth = useCallback((next: number) => {
    const clamped = clampDrawerWidth(next, viewportWidth());
    setWidthState(clamped);
    storeDrawerWidth(clamped);
    if (clamped !== DEFAULT_AI_DRAWER_WIDTH) lastCustomRef.current = clamped;
  }, []);

  const resetWidth = useCallback(() => setWidth(DEFAULT_AI_DRAWER_WIDTH), [setWidth]);

  const toggleWidth = useCallback(() => {
    if (width === DEFAULT_AI_DRAWER_WIDTH) {
      // No custom width yet: the useful other end is as wide as it goes.
      setWidth(lastCustomRef.current ?? maxDrawerWidth(viewportWidth()));
      return;
    }
    setWidthState(DEFAULT_AI_DRAWER_WIDTH);
    storeDrawerWidth(DEFAULT_AI_DRAWER_WIDTH);
  }, [setWidth, width]);

  const setDragging = useCallback((dragging: boolean) => {
    document.documentElement.classList.toggle(AI_DRAWER_DRAGGING_CLASS, dragging);
  }, []);

  // Seed the toggle's "other" width from what the viewer chose last time,
  // so the first Enter after a reload goes back to their width rather than
  // to the widest one.
  useEffect(() => {
    const stored = readStoredDrawerWidth();
    if (stored === null) return;
    const clamped = clampDrawerWidth(stored, viewportWidth());
    if (clamped !== DEFAULT_AI_DRAWER_WIDTH) lastCustomRef.current = clamped;
  }, []);

  // Publish the width for the page's reservation.
  useEffect(() => {
    document.documentElement.style.setProperty(AI_DRAWER_WIDTH_VAR, `${width}px`);
  }, [width]);

  // Only an open drawer reserves anything.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle(AI_DRAWER_OPEN_CLASS, isOpen);
    return () => root.classList.remove(AI_DRAWER_OPEN_CLASS);
  }, [isOpen]);

  // A window that shrinks must not leave the drawer over the page.
  useEffect(() => {
    const onResize = () => {
      setMaxWidth(maxDrawerWidth(window.innerWidth));
      setWidthState((current) => clampDrawerWidth(current, window.innerWidth));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return { width, minWidth: MIN_AI_DRAWER_WIDTH, maxWidth, setWidth, toggleWidth, resetWidth, setDragging };
}
