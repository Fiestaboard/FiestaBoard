"use client";

import { useSyncExternalStore } from "react";

/**
 * The web app's one coarse-pointer signal (owned by web slice 2.6; 2.4 ships a
 * byte-identical copy so the stack merges cleanly).
 *
 * True when the primary pointer is a finger. Touch layouts take the 44px
 * targets and touch copy that 07 `57:66920` draws; a mouse, trackpad or pen
 * keeps the denser desktop rows and keyboard hints. Use it where a component
 * takes a `size` prop. For pure styling, Tailwind's `pointer-coarse:` variant
 * reads the same media query.
 *
 * Built on `useSyncExternalStore`, so the first render already has the real
 * answer (the app is a client-only SPA) and a phone never paints one frame of
 * desktop rows. It follows changes live (a tablet that docks a trackpad). With
 * no `matchMedia`, and on the server, it is false.
 *
 * TODO(FiestaUI): retire this once the kit decides it (`size="auto"` on
 * ListRow / ListRowGroup / SortableList, or an exported `useCoarsePointer`).
 */
const COARSE_POINTER_QUERY = "(pointer: coarse)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(COARSE_POINTER_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(COARSE_POINTER_QUERY).matches
    : false;
}

function getServerSnapshot(): boolean {
  return false;
}

export function useCoarsePointer(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
