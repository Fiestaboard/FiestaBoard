"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * Reads display animation settings from the API and toggles classes on
 * <html> so CSS can selectively suppress motion:
 *
 *   .reduce-motion          — accessibility override; kills all animations
 *   .site-animations-off    — user disabled general UI motion
 *   .board-animations-off   — user disabled the split-flap animation
 *
 * `site-animations-off` mirrors `reduce-motion` for app-wide motion but
 * is separate so users can still see the board flap when they only want
 * the rest of the UI to stay still.
 */
export function ReduceMotionApplier() {
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const display = allSettings?.display;
  const reduceMotion = display?.reduce_motion ?? false;
  const boardAnimations = display?.board_animations ?? "on";
  const siteAnimations = display?.site_animations ?? "on";

  useEffect(() => {
    const html = document.documentElement;
    html.classList.toggle("reduce-motion", reduceMotion);
    // reduce_motion is the master kill switch — it implies site + board off
    html.classList.toggle(
      "site-animations-off",
      reduceMotion || siteAnimations === "off",
    );
    html.classList.toggle(
      "board-animations-off",
      reduceMotion || boardAnimations === "off",
    );
    html.classList.toggle(
      "board-animations-desktop-only",
      !reduceMotion && boardAnimations === "desktop",
    );
  }, [reduceMotion, boardAnimations, siteAnimations]);

  return null;
}
