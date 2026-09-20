"use client";

import { useEffect, useState } from "react";

/**
 * True when the user has asked for less motion — either through the OS
 * (`prefers-reduced-motion: reduce`) or through FiestaBoard's own Reduce
 * motion setting, which `ReduceMotionApplier` publishes as a class on
 * `<html>`. Both are watched live, so turning either on mid-walkthrough
 * makes the rest of it instant.
 */
export const REDUCE_MOTION_CLASS = "reduce-motion";

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const html = document.documentElement;
    const update = () => setReduced(!!query?.matches || html.classList.contains(REDUCE_MOTION_CLASS));
    update();
    query?.addEventListener("change", update);
    // The in-app setting lands as a class, so the class is what we watch.
    const observer = new MutationObserver(update);
    observer.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => {
      query?.removeEventListener("change", update);
      observer.disconnect();
    };
  }, []);

  return reduced;
}
