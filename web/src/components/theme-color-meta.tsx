"use client";

import { useTheme } from "@/hooks/use-theme";
import { useEffect } from "react";

/**
 * Resolves any CSS color value (including oklch) to a hex string
 * by leveraging the browser's computed style resolution.
 */
function cssColorToHex(cssColor: string): string {
  const el = document.createElement("div");
  el.style.display = "none";
  el.style.color = cssColor;
  document.body.appendChild(el);
  const computed = getComputedStyle(el).color;
  el.remove();

  const m = computed.match(/[\d.]+/g);
  if (!m || m.length < 3) return "#000000";
  return (
    "#" +
    m
      .slice(0, 3)
      .map((n) => Math.round(Number(n)).toString(16).padStart(2, "0"))
      .join("")
  );
}

/**
 * Syncs `<meta name="theme-color">` with the current theme's --background
 * CSS variable so iOS Safari / Android Chrome paint the status bar / address
 * bar to match the app header.
 *
 * On SSR, static `<meta>` tags with `media` queries handle the initial render.
 * Once hydrated this component takes over and sets a single authoritative value
 * based on the resolved theme (which may differ from the system preference).
 */
export function ThemeColorMeta() {
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!resolvedTheme) return;

    const bgRaw = getComputedStyle(document.documentElement).getPropertyValue("--background").trim();
    if (!bgRaw) return;

    const hex = cssColorToHex(bgRaw);

    const existing = document.querySelectorAll('meta[name="theme-color"]');

    if (existing.length === 1 && !existing[0].getAttribute("media")) {
      (existing[0] as HTMLMetaElement).content = hex;
      return;
    }

    existing.forEach((el) => el.remove());
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    meta.content = hex;
    document.head.appendChild(meta);
  }, [resolvedTheme]);

  return null;
}
