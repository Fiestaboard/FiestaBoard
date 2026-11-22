"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * 07e Accessibility › "Motion and reading · For this browser." (`333:57132`).
 *
 * Four switches that belong to this browser, not the hub, so they live in
 * localStorage (like the theme) and another tab follows a change.
 *
 * - `reduceMotion`: 07e "Follows your phone's setting": never set, it reads the
 *   OS `prefers-reduced-motion`; once switched, the choice is stored. It adds
 *   to the hub-wide `display.reduce_motion`, never overrides it: either one on
 *   means no motion (DESIGN-DELTAS DD-W153, Jev `or_union`).
 * - `readAloud`: Home's live board announces each change through the kit's
 *   polite live region (`announceUpdates`).
 * - `largeTargets`: retunes the kit's `--touch-target` to 48 px.
 * - `boardContrast`: board-black glyphs take the board's own white.
 */
export type BrowserA11yPref = "reduceMotion" | "readAloud" | "largeTargets" | "boardContrast";

export const BROWSER_A11Y_KEYS: Record<BrowserA11yPref, string> = {
  reduceMotion: "fiestaboard_a11y_reduce_motion",
  readAloud: "fiestaboard_a11y_read_aloud",
  largeTargets: "fiestaboard_a11y_large_targets",
  boardContrast: "fiestaboard_a11y_board_contrast",
};

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/** The stored choice, or null when this browser never set one. */
function stored(pref: BrowserA11yPref): boolean | null {
  try {
    const value = localStorage.getItem(BROWSER_A11Y_KEYS[pref]);
    return value === "on" ? true : value === "off" ? false : null;
  } catch {
    return null;
  }
}

function osReducesMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.(REDUCED_MOTION_QUERY).matches;
}

/** The effective value of one preference in this browser. */
export function readBrowserA11y(pref: BrowserA11yPref): boolean {
  const value = stored(pref);
  if (value !== null) return value;
  return pref === "reduceMotion" ? osReducesMotion() : false;
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  const keys = Object.values(BROWSER_A11Y_KEYS);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || keys.includes(event.key)) listener();
  };
  const mql = window.matchMedia?.(REDUCED_MOTION_QUERY);
  window.addEventListener("storage", onStorage);
  mql?.addEventListener("change", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
    mql?.removeEventListener("change", listener);
  };
}

/** Write one preference for this browser and tell every reader in this tab. */
export function setBrowserA11y(pref: BrowserA11yPref, on: boolean) {
  try {
    localStorage.setItem(BROWSER_A11Y_KEYS[pref], on ? "on" : "off");
  } catch {}
  for (const listener of listeners) listener();
}

/** One preference, live, and its setter. */
export function useBrowserA11y(pref: BrowserA11yPref): [boolean, (on: boolean) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => readBrowserA11y(pref),
    () => false,
  );
  const set = useCallback((on: boolean) => setBrowserA11y(pref, on), [pref]);
  return [value, set];
}
