"use client";

import { useEffect, useState } from "react";

/**
 * Returns whether the `pride-month` class is currently on `<html>`.
 *
 * The class is the single gate for Pride Month UI flourishes — applied
 * by the root layout (`web/app/root.tsx::Layout`) on first mount, based
 * on the date + the `hide_festive_months` cookie. JS-rendered
 * decorations (sidebar aurora, click-to-celebrate confetti) read from
 * this hook so they stay in lockstep with the CSS rules that key off
 * the same class.
 *
 * The class only changes via a full page load (the settings toggle
 * sets the cookie and reloads), so reading it once on mount is enough.
 * Returns false during the first render to avoid any hydration-style
 * mismatch for anything mounted inside this hook's consumer.
 */
export function usePrideActive(): boolean {
  const [active, setActive] = useState(false);

  useEffect(() => {
    setActive(document.documentElement.classList.contains("pride-month"));
  }, []);

  return active;
}
