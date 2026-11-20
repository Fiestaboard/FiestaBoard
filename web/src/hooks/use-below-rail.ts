"use client";

import { useLayoutEffect, useRef, useSyncExternalStore } from "react";

/**
 * Where the phone chrome hands over to the rail (slice 2.1, WEB-02): the
 * bottom tab bar below 768px, the rail from 768px. This is the same pixel as
 * the Sidebar's and MainContent's `railBreakpoint="md"`; keep them together.
 */
export const RAIL_BREAKPOINT = "md" as const;

/**
 * A viewport too short for the rail to list every destination: a phone on
 * its side (844×390). It keeps the bottom tab bar up to the `lg` breakpoint
 * instead (BB-A-13).
 */
export const SHORT_VIEWPORT_QUERY = "(max-height: 499.98px)";
export const BELOW_RAIL_QUERY = "(max-width: 767.98px)";
/** Below the `lg` rail: with a short viewport, still the tab bar (BB-A-13). */
const BELOW_LG_QUERY = "(max-width: 1023.98px)";

const matches = (query: string) => window.matchMedia?.(query)?.matches ?? false;

/** Subscribe to several media queries at once. */
function subscribeAll(queries: string[]) {
  return (onChange: () => void) => {
    const lists = queries.map((q) => window.matchMedia?.(q));
    lists.forEach((list) => list?.addEventListener?.("change", onChange));
    return () => lists.forEach((list) => list?.removeEventListener?.("change", onChange));
  };
}

function subscribeShort(onChange: () => void) {
  const query = window.matchMedia?.(SHORT_VIEWPORT_QUERY);
  query?.addEventListener?.("change", onChange);
  return () => query?.removeEventListener?.("change", onChange);
}

/**
 * The breakpoint the Sidebar, MainContent and PageLayout take: `md` (the tab
 * bar below 768px), or `lg` on a short viewport so a landscape phone keeps
 * the tab bar. Keep every chrome piece on this one value.
 */
export function useRailBreakpoint(): "md" | "lg" {
  const short = useSyncExternalStore(
    subscribeShort,
    () => window.matchMedia?.(SHORT_VIEWPORT_QUERY)?.matches ?? false,
    () => false,
  );
  return short ? "lg" : RAIL_BREAKPOINT;
}

const subscribe = subscribeAll([BELOW_RAIL_QUERY, BELOW_LG_QUERY, SHORT_VIEWPORT_QUERY]);

function getSnapshot() {
  return matches(BELOW_RAIL_QUERY) || (matches(SHORT_VIEWPORT_QUERY) && matches(BELOW_LG_QUERY));
}

/**
 * True while the viewport is phone width, i.e. the tab bar is the nav. Read
 * synchronously on the first render (the app is a client-only SPA), so the
 * phone never paints the rail's list first.
 */
export function useBelowRail(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}

/** The tablet band: the rail is on screen but a 256px rail would crowd the page. */
export const TABLET_RAIL_QUERY = "(min-width: 768px) and (max-width: 1023.98px)";

const subscribeTablet = subscribeAll([TABLET_RAIL_QUERY, SHORT_VIEWPORT_QUERY]);

/** In the band, and tall enough to have the rail at all (a short one keeps the tab bar). */
function getTabletSnapshot() {
  return matches(TABLET_RAIL_QUERY) && !matches(SHORT_VIEWPORT_QUERY);
}

/**
 * From 768 to 1023px the rail starts collapsed (07 `61:17544`, 07a
 * `307:61752`: the 900 frames draw the 64px rail). It is a default, not a
 * lock: the reader can still expand it there. Nothing done in the band is
 * persisted (the caller's toggle must pass `persist: false` while this
 * returns true), and on leaving the band the rail goes back to the state the
 * reader chose for wide screens.
 *
 * Runs in a layout effect, so a page opened in the band never paints the
 * 256px rail before collapsing it.
 *
 * @returns whether the viewport is in the tablet band.
 */
export function useTabletRailCollapse(
  setCollapsed: (value: boolean, opts?: { persist?: boolean }) => void,
  readStored: () => boolean,
): boolean {
  const inBand = useSyncExternalStore(subscribeTablet, getTabletSnapshot, () => false);
  const previous = useRef<boolean | null>(null);
  useLayoutEffect(() => {
    if (previous.current === inBand) return;
    const first = previous.current === null;
    previous.current = inBand;
    if (inBand) setCollapsed(true, { persist: false });
    else if (!first) setCollapsed(readStored(), { persist: false });
  }, [inBand, setCollapsed, readStored]);
  return inBand;
}
