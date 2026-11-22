"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { useBrowserA11y } from "@/hooks/use-browser-a11y";
import { api } from "@/lib/api";
import { isChromelessPath } from "@/lib/chromeless";

/**
 * Reads display animation settings from the API and toggles classes on
 * <html> so CSS can selectively suppress motion:
 *
 *   .reduce-motion          — accessibility override; kills all animations
 *   .site-animations-off    — user disabled general UI motion
 *   .board-animations-off   — user disabled the split-flap animation
 *   .a11y-large-targets     — this browser's Larger touch targets (07e)
 *   .a11y-board-high-contrast — this browser's High-contrast board text (07e)
 *
 * Reduce motion is on when the hub turns it on for everyone OR this browser
 * does (07e "For this browser", BB-FC-12; DESIGN-DELTAS DD-W153).
 *
 * `site-animations-off` mirrors `reduce-motion` for app-wide motion but
 * is separate so users can still see the board flap when they only want
 * the rest of the UI to stay still.
 */
export function ReduceMotionApplier() {
  // The FiestaPanel TV viewer must not fire this authenticated query — see
  // CurrentBoardProvider for why this reads window.location, not useLocation().
  const chromeless = typeof window !== "undefined" && isChromelessPath(window.location.pathname);
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
    enabled: !chromeless,
  });

  const display = allSettings?.display;
  const [browserReduce] = useBrowserA11y("reduceMotion");
  const [largeTargets] = useBrowserA11y("largeTargets");
  const [boardContrast] = useBrowserA11y("boardContrast");
  const reduceMotion = (display?.reduce_motion ?? false) || browserReduce;
  const boardAnimations = display?.board_animations ?? "on";
  const siteAnimations = display?.site_animations ?? "on";

  useEffect(() => {
    const html = document.documentElement;
    html.classList.toggle("reduce-motion", reduceMotion);
    // reduce_motion is the master kill switch — it implies site + board off
    html.classList.toggle("site-animations-off", reduceMotion || siteAnimations === "off");
    html.classList.toggle("board-animations-off", reduceMotion || boardAnimations === "off");
    html.classList.toggle("board-animations-desktop-only", !reduceMotion && boardAnimations === "desktop");
  }, [reduceMotion, boardAnimations, siteAnimations]);

  useEffect(() => {
    const html = document.documentElement;
    html.classList.toggle("a11y-large-targets", largeTargets);
    html.classList.toggle("a11y-board-high-contrast", boardContrast);
  }, [largeTargets, boardContrast]);

  return null;
}
