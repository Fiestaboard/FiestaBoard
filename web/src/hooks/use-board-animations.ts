"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

const DESKTOP_QUERY = "(min-width: 768px)";

/**
 * Returns true when the split-flap board animation should run, given the
 * user's display settings and the current viewport. Centralised so the
 * CSS kill-switch and the JS render gate agree on the same conditions.
 *
 * Falsy when:
 *   - reduce_motion is on (accessibility override)
 *   - board_animations === "off"
 *   - board_animations === "desktop" AND viewport is below 768px
 *
 * Defaults to `true` while settings are loading so the first paint
 * matches the prior behaviour rather than briefly snapping tiles.
 */
export function useBoardAnimationsEnabled(): boolean {
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.matchMedia(DESKTOP_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mql = window.matchMedia(DESKTOP_QUERY);
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  const display = allSettings?.display;
  if (!display) return true;
  if (display.reduce_motion) return false;
  const mode = display.board_animations ?? "on";
  if (mode === "off") return false;
  if (mode === "desktop" && !isDesktop) return false;
  return true;
}
