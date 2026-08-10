"use client";

import { FLAP_SPEED_PRESETS, type FlapSpeed, type FlapSpeedPreset } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

const DESKTOP_QUERY = "(min-width: 768px)";
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/** Subscribe to a media query, SSR-safe, with `fallback` before hydration. */
function useMediaQuery(query: string, fallback: boolean): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return fallback;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    // No initial re-sync here: the initializer above already read the query on
    // the client, and setting state in an effect body only costs a cascading
    // render. Subscribe and let `change` do the rest.
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

/**
 * Returns true when the split-flap board animation should run, given the
 * user's display settings and the current viewport. Centralised so the
 * CSS kill-switch and the JS render gate agree on the same conditions.
 *
 * Falsy when:
 *   - the OS/browser reports `prefers-reduced-motion: reduce`
 *   - reduce_motion is on (accessibility override)
 *   - board_animations === "off"
 *   - board_animations === "desktop" AND viewport is below 768px
 *
 * `prefers-reduced-motion` is decided here rather than left to CSS. A message
 * change is not one animation, it is a cascade: every changed tile steps
 * through the character drum one glyph per flap step, so a tile going from
 * index 5 to index 40 runs 35 consecutive flips. The global
 * `prefers-reduced-motion` catch-all in globals.css (which forces
 * `animation-duration: 0.01ms`) cannot help with that — it only truncates each
 * individual CSS flap and leaves the JS-driven glyph cascade intact, which is
 * a seconds-long strobe with the motion smoothing removed. Under `reduce` the
 * board snaps per tile instead. Matches FiestaUI issue #180.
 *
 * Defaults to `true` while settings are loading so the first paint
 * matches the prior behaviour rather than briefly snapping tiles.
 */
export function useBoardAnimationsEnabled(): boolean {
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const isDesktop = useMediaQuery(DESKTOP_QUERY, true);
  const prefersReducedMotion = useMediaQuery(REDUCED_MOTION_QUERY, false);

  if (prefersReducedMotion) return false;

  const display = allSettings?.display;
  if (!display) return true;
  if (display.reduce_motion) return false;
  const mode = display.board_animations ?? "on";
  if (mode === "off") return false;
  if (mode === "desktop" && !isDesktop) return false;
  return true;
}

/** The stored setting is a preset name, or a raw millisecond count. */
function isFlapSpeedPreset(value: string): value is FlapSpeedPreset {
  return Object.prototype.hasOwnProperty.call(FLAP_SPEED_PRESETS, value);
}

/**
 * Normalise a persisted `board_flap_speed` value into a {@link FlapSpeed}.
 *
 * The settings UI only ever writes one of the four preset names. A raw number
 * (or numeric string) is the escape hatch: the API accepts it so an advanced
 * user or the AI settings tool can pick a cadence the UI does not offer, and
 * `resolveFlapSpeed` clamps it to [8, 2000]. Anything unrecognised falls back
 * to the default rather than throwing in a render.
 */
export function parseFlapSpeedSetting(value: unknown): FlapSpeed {
  if (typeof value === "number" && Number.isFinite(value)) return { durationMs: value };
  if (typeof value === "string") {
    if (isFlapSpeedPreset(value)) return value;
    const numeric = Number(value);
    if (value.trim() !== "" && Number.isFinite(numeric)) return { durationMs: numeric };
  }
  return "standard";
}

/**
 * The user's chosen split-flap cadence, as a {@link FlapSpeed}.
 *
 * Defaults to `"standard"` (80ms — what this app has always shipped) while
 * settings are loading and whenever the stored value is missing or unusable,
 * so a board never renders at a cadence the user did not ask for.
 */
export function useBoardFlapSpeed(): FlapSpeed {
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  return parseFlapSpeedSetting(allSettings?.display?.board_flap_speed);
}
