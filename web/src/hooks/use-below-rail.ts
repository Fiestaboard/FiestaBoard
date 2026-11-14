"use client";

import { useEffect, useSyncExternalStore } from "react";

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

/**
 * From 768 to 1023px the rail starts collapsed (07 `61:17544`, 07a
 * `307:61752`: the 900 frames draw the 64px rail). It is a default, not a
 * lock: the reader can still expand it there, and on leaving the band the rail
 * goes back to the state they chose for wide screens. Neither change is
 * persisted, so the wide-screen preference is never overwritten by a tablet.
 */
export function useTabletRailCollapse(
  setCollapsed: (value: boolean, opts?: { persist?: boolean }) => void,
  readStored: () => boolean,
): void {
  useEffect(() => {
    const query = window.matchMedia?.(TABLET_RAIL_QUERY);
    if (!query) return;
    let inBand = query.matches;
    if (inBand) setCollapsed(true, { persist: false });
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches === inBand) return;
      inBand = event.matches;
      setCollapsed(inBand ? true : readStored(), { persist: false });
    };
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, [setCollapsed, readStored]);
}
