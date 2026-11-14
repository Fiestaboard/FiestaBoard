"use client";

import { useEffect, useState } from "react";

const COARSE_POINTER = "(pointer: coarse)";

/**
 * True when the primary pointer is a finger. Touch layouts take the 44px
 * targets (`size="touch"`) that 07 `57:66920` draws; a mouse or pen keeps the
 * denser desktop rows. Watched live, so a tablet that docks a trackpad
 * follows along. False on the server and until the first effect.
 */
export function useCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(COARSE_POINTER);
    const update = () => setCoarse(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  return coarse;
}
