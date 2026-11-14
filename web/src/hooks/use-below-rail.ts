"use client";

import { useLayoutEffect, useRef, useSyncExternalStore } from "react";

/**
 * Where the phone chrome hands over to the rail (slice 2.1, WEB-02): the
 * bottom tab bar below 768px, the rail from 768px. This is the same pixel as
 * the Sidebar's and MainContent's `railBreakpoint="md"`; keep them together.
 */
export const RAIL_BREAKPOINT = "md" as const;
export const BELOW_RAIL_QUERY = "(max-width: 767.98px)";

function subscribe(onChange: () => void) {
  const query = window.matchMedia?.(BELOW_RAIL_QUERY);
  query?.addEventListener?.("change", onChange);
  return () => query?.removeEventListener?.("change", onChange);
}

function getSnapshot() {
  return window.matchMedia?.(BELOW_RAIL_QUERY)?.matches ?? false;
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

function subscribeTablet(onChange: () => void) {
  const query = window.matchMedia?.(TABLET_RAIL_QUERY);
  query?.addEventListener?.("change", onChange);
  return () => query?.removeEventListener?.("change", onChange);
}

function getTabletSnapshot() {
  return window.matchMedia?.(TABLET_RAIL_QUERY)?.matches ?? false;
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
