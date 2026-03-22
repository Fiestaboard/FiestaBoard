"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * Reads the `display.reduce_motion` setting from the API and toggles the
 * `reduce-motion` class on <html> so that CSS can mirror the behaviour of
 * `@media (prefers-reduced-motion: reduce)` as an app-level override.
 */
export function ReduceMotionApplier() {
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const reduceMotion = allSettings?.display?.reduce_motion ?? false;

  useEffect(() => {
    const html = document.documentElement;
    if (reduceMotion) {
      html.classList.add("reduce-motion");
    } else {
      html.classList.remove("reduce-motion");
    }
  }, [reduceMotion]);

  return null;
}
