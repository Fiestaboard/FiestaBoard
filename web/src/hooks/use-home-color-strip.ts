"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * "Show the color strip on Home" (07e Appearance › Boards, `333:56102`).
 *
 * A browser preference like the theme: it lives in this browser's
 * localStorage, not on the hub. On by default, as 07e draws the switch.
 */
export const HOME_COLOR_STRIP_KEY = "fiestaboard_home_color_strip";

const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return localStorage.getItem(HOME_COLOR_STRIP_KEY) !== "off";
  } catch {
    return true;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  // Another tab changed it.
  const onStorage = (event: StorageEvent) => {
    if (event.key === HOME_COLOR_STRIP_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Whether Home draws its colour strip, and a setter that remembers the choice. */
export function useHomeColorStrip(): [boolean, (show: boolean) => void] {
  const show = useSyncExternalStore(subscribe, read, () => true);
  const setShow = useCallback((next: boolean) => {
    try {
      localStorage.setItem(HOME_COLOR_STRIP_KEY, next ? "on" : "off");
    } catch {}
    for (const listener of listeners) listener();
  }, []);
  return [show, setShow];
}
