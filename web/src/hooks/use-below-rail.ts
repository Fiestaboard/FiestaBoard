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
 * Where the rail starts collapsed without the reader asking, and gives their
 * own choice back afterwards. Two holds, either of which collapses it:
 *
 * - The tablet band, 768–1023px (07 `61:17544`, 07a `307:61752`: the 900
 *   frames draw the 64px rail). Nothing toggled in the band is persisted
 *   (the caller's toggle passes `persist: false` while this returns true,
 *   DD-W46).
 * - The page editor (`inEditor`), at any width: every Figma editor frame
 *   draws the icon rail (53:137378, 184:159319; owner decision D1, BB-E-3).
 *   A toggle there is the reader's explicit choice and persists through the
 *   Sidebar's own toggle, so it becomes the global choice.
 *
 * Entering either hold collapses the rail for the visit (without persisting).
 * Moving within the editor (new page to saved page) is not an entry. When the
 * last hold lets go, the rail goes back to the stored global choice, which
 * already includes any toggle the reader made in the editor.
 *
 * Runs in a layout effect, so a page opened in a hold never paints the 256px
 * rail before collapsing it.
 *
 * @returns whether the viewport is in the tablet band.
 */
export function useRailAutoCollapse(
  setCollapsed: (value: boolean, opts?: { persist?: boolean }) => void,
  readStored: () => boolean,
  inEditor = false,
): boolean {
  const inBand = useSyncExternalStore(subscribeTablet, getTabletSnapshot, () => false);
  const previous = useRef<{ band: boolean; editor: boolean } | null>(null);
  useLayoutEffect(() => {
    const before = previous.current;
    if (before && before.band === inBand && before.editor === inEditor) return;
    previous.current = { band: inBand, editor: inEditor };
    const entered = (inBand && !before?.band) || (inEditor && !before?.editor);
    if (entered) setCollapsed(true, { persist: false });
    else if (before && !inBand && !inEditor) setCollapsed(readStored(), { persist: false });
  }, [inBand, inEditor, setCollapsed, readStored]);
  return inBand;
}
