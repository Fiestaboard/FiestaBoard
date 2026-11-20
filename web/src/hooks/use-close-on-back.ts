"use client";

import { useEffect, useId, useRef } from "react";

const KEY = "fbOverlay";

function ourEntryOnTop(id: string): boolean {
  const state: unknown = window.history.state;
  return !!state && typeof state === "object" && (state as Record<string, unknown>)[KEY] === id;
}

function pushEntry(id: string): void {
  const state: unknown = window.history.state;
  window.history.pushState({ ...(state && typeof state === "object" ? state : {}), [KEY]: id }, "");
}

/**
 * Back closes an open sheet or dialog instead of leaving the screen
 * (BB-A-12, the Android convention for modal sheets).
 *
 * While `open`, one history entry is pushed for the overlay (same URL, the
 * router's own state kept). Back pops it, and the overlay closes. Closed any
 * other way (its X, the scrim, a submit), the entry is taken back so the
 * history is as it was. If the overlay closes because the app navigated
 * somewhere else, the entry is no longer on top and is left alone.
 *
 * Taking the entry back is deferred a task: an effect that runs again at once
 * (StrictMode's mount check, or a close and reopen in one go) keeps the same
 * entry instead of racing a Back against a new push. A popstate only closes
 * the overlay when its entry is no longer on top. history.back() lands
 * asynchronously, so an overlay reopened before it does ignores that Back's
 * popstate and pushes its entry again once it lands.
 */
export function useCloseOnBack(open: boolean, close: () => void): void {
  const id = useId();
  const closeRef = useRef(close);
  useEffect(() => {
    closeRef.current = close;
  }, [close]);
  const pendingBack = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backInFlight = useRef(false);
  const openRef = useRef(open);
  useEffect(() => {
    openRef.current = open;
  }, [open]);
  useEffect(() => {
    if (!open || typeof window === "undefined") return;
    if (pendingBack.current !== null) {
      clearTimeout(pendingBack.current);
      pendingBack.current = null;
    }
    if (!backInFlight.current && !ourEntryOnTop(id)) pushEntry(id);
    const onPop = () => {
      if (!backInFlight.current && !ourEntryOnTop(id)) closeRef.current();
    };
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      pendingBack.current = setTimeout(() => {
        pendingBack.current = null;
        if (!ourEntryOnTop(id)) return;
        backInFlight.current = true;
        window.addEventListener(
          "popstate",
          () => {
            backInFlight.current = false;
            if (openRef.current && !ourEntryOnTop(id)) pushEntry(id);
          },
          { once: true },
        );
        window.history.back();
      }, 0);
    };
  }, [open, id]);
  useEffect(
    () => () => {
      if (pendingBack.current !== null) clearTimeout(pendingBack.current);
    },
    [],
  );
}
