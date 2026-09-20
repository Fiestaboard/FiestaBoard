"use client";

import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { CircleCheckIcon, InfoIcon, OctagonXIcon, TriangleAlertIcon } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useOptionalGlobalAiPanel } from "@/components/global-ai-panel-context";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";

/** Where the drawer stops being a panel beside the page and becomes the page. */
const DESKTOP_QUERY = "(min-width: 1024px)";

/**
 * Read through `useSyncExternalStore` rather than an effect: the value is
 * external state, so React reads it during render on the client and uses
 * the server snapshot (false) while hydrating — no cascading re-render on
 * mount, and no hydration mismatch.
 */
function subscribeToDesktop(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(DESKTOP_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function isDesktopNow(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(DESKTOP_QUERY).matches;
}

function useMatchesDesktop(): boolean {
  return useSyncExternalStore(subscribeToDesktop, isDesktopNow, () => false);
}

/**
 * App-wide Sonner wrapper.
 *
 * Sonner renders a single `<section aria-live="polite" aria-label="…">`
 * for all toast announcements. By default that label is the English string
 * "Notifications", which screen readers then announce verbatim under any
 * `<html lang>` (Spanish, Japanese, etc.). Forward the translated label
 * through `containerAriaLabel` so the region announcement matches the
 * active locale.
 *
 * Accessibility:
 *   WCAG 3.1.2 Language of Parts — assistive tech now hears the region
 *   label in the user's chosen language. Sonner still appends the
 *   keyboard-shortcut hint ("alt+T") to the label; that suffix is
 *   universal notation and is left as-is.
 *
 * Callers may still override `containerAriaLabel` via props if they need a
 * more specific label for a particular Toaster instance.
 */
const Toaster = ({ containerAriaLabel, ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();
  const t = useTranslations("common");
  const ariaLabel = containerAriaLabel ?? t("notificationsRegionLabel");

  // Toasts and the FiestaBot drawer both live in the bottom-right corner,
  // so a "Schedule created · Undo" landed on top of the composer the user
  // was still typing in (#2024). While the drawer is open the toasts step
  // out of its way: beside it on a wide screen, where there is room, and to
  // the top of the screen on a phone, where the drawer IS the screen.
  const aiPanel = useOptionalGlobalAiPanel();
  const isDesktop = useMatchesDesktop();
  const drawerOpen = aiPanel?.isOpen ?? false;
  const position: ToasterProps["position"] =
    drawerOpen && !isDesktop ? "top-center" : (props.position ?? "bottom-right");
  // The drawer's live width plus its inset and a gap of the same size.
  const offset = drawerOpen && isDesktop ? { right: "calc(var(--ai-drawer-width, 384px) + 1.5rem)" } : props.offset;

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      containerAriaLabel={ariaLabel}
      position={position}
      offset={offset}
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Spinner label={null} />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
