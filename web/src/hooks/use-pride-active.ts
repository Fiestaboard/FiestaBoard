"use client";

import { useEffect, useState } from "react";

import { readCookieString, shouldShowPride } from "@/lib/pride";

/**
 * Returns whether Pride Month flourishes should be active.
 *
 * Derives from the same primary source as the `pride-month` CSS class
 * (date + `hide_festive_months` cookie) rather than reading the class
 * itself — that keeps the JS gate (sidebar aurora, click-to-celebrate
 * confetti) and the CSS gate aligned even when the prerendered HTML
 * has the class baked in but the user has opted out via cookie.
 *
 * Pre-fix the hook read `document.documentElement.classList` once on
 * mount, which meant after toggling the cookie + reloading, the JS
 * decorations stayed visible whenever the SSR/prerender output had
 * already included `pride-month` on `<html>`.
 *
 * The hook returns `false` on the first render to avoid hydration
 * mismatch for anything mounted inside its consumer, then resolves
 * to the cookie-aware value in a layout effect.
 */
export function usePrideActive(): boolean {
  const [active, setActive] = useState(false);

  useEffect(() => {
    setActive(shouldShowPride(new Date(), readCookieString()));
  }, []);

  return active;
}
