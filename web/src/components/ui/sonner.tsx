"use client";

import {
  Toaster as KitToaster,
  type ToasterProps as KitToasterProps,
} from "@fiestaboard/ui/components/feedback/toaster";
import { useContext, useSyncExternalStore } from "react";
import { UNSAFE_LocationContext } from "react-router";

import { useOptionalSpotlight } from "@/components/ai-spotlight/spotlight-provider";
import { useOptionalGlobalAiPanel } from "@/components/global-ai-panel-context";
import { useBelowRail } from "@/hooks/use-below-rail";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

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

/** Clears the phone editor's bottom touch toolbar. */
const EDITOR_PHONE_OFFSET = { bottom: "calc(64px + env(safe-area-inset-bottom))" };

/** The page editor (a new page, or one being edited). */
const EDITOR_ROUTE = /\/pages\/(new|edit)(\/|$)/;

/**
 * Whether the page editor is on screen. Read from the router's context
 * without `useLocation`, which throws outside a router (Storybook, tests).
 */
function useOnEditorRoute(): boolean {
  const pathname = useContext(UNSAFE_LocationContext)?.location?.pathname ?? "";
  return EDITOR_ROUTE.test(pathname);
}

/** Public kit props, plus the existing app live-region label alias.
 * General Sonner presentation props are owned by the kit rather than this host.
 */
type ToasterProps = KitToasterProps & { containerAriaLabel?: string };

/**
 * App-wide kit toast host.
 *
 * Sonner renders a single `<section aria-live="polite" aria-label="…">`
 * for all toast announcements. By default that label is the English string
 * "Notifications", which screen readers then announce verbatim under any
 * `<html lang>` (Spanish, Japanese, etc.). Forward the translated label
 * through the kit labels so the region announcement matches the
 * active locale.
 *
 * Accessibility:
 *   WCAG 3.1.2 Language of Parts — assistive tech now hears the region
 *   label in the user's chosen language. Sonner still appends the
 *   keyboard-shortcut hint ("alt+T") to the label; that suffix is
 *   universal notation and is left as-is.
 *
 * Callers may still override `containerAriaLabel` via props if they need a
 * more specific label for a particular Toaster instance. The kit labels
 * API also remains available; the legacy alias takes precedence.
 */
const Toaster = ({ containerAriaLabel, labels, ...props }: ToasterProps) => {
  const { resolvedTheme } = useTheme();
  const t = useTranslations("common");
  const ariaLabel = containerAriaLabel ?? labels?.container ?? t("notificationsRegionLabel");

  // Toasts and the FiestaBot drawer both live in the bottom-right corner,
  // so a "Schedule created · Undo" landed on top of the composer the user
  // was still typing in (#2024). While the drawer is open the toasts step
  // out of its way: beside it on a wide screen, where there is room, and to
  // the top of the screen on a phone, where the drawer IS the screen.
  const aiPanel = useOptionalGlobalAiPanel();
  const isDesktop = useMatchesDesktop();
  const drawerOpen = aiPanel?.isOpen ?? false;

  // A walkthrough's caption is fixed at the bottom centre and carries the
  // Stop button that ends it (#2010). Stepping left of the drawer puts a
  // toast exactly there, and a toast over Stop takes away the only way out
  // of a walkthrough — so while one is on screen the toasts go to the top
  // and leave the bottom to it.
  const walkthroughOnScreen = useOptionalSpotlight()?.active ?? false;

  // BB-FS-7 (07a `311:73476`, 07c `316:91196`, kit Toast "top-right from
  // sm"): from the rail up a toast drops in at the top right; on a phone it
  // rises from the bottom, above the tab bar (the kit clears the bar).
  const belowRail = useBelowRail();
  // UX-8-2 (306:30304): in the page editor a toast is a bottom-right card, clear
  // of Export · Save · Show now in the header, and under the modal layer so it
  // never sits on a dialog's scrim.
  const onEditor = useOnEditorRoute();
  const position: ToasterProps["position"] =
    props.position ??
    (walkthroughOnScreen || aiPanel?.isMinimized || (drawerOpen && !isDesktop)
      ? "top-center"
      : belowRail || onEditor
        ? "bottom-right"
        : "top-right");
  // The drawer's live width plus its inset and a gap of the same size.
  const offset =
    props.offset ??
    (drawerOpen && isDesktop && !walkthroughOnScreen
      ? { right: "calc(var(--ai-drawer-width, 384px) + 1.5rem)" }
      : onEditor && !belowRail && position === "bottom-right"
        ? 24
        : onEditor && belowRail && position === "bottom-right"
          ? EDITOR_PHONE_OFFSET
          : undefined);
  // A phone editor keeps its touch toolbar at the bottom: toasts rise above it (W-3).
  const mobileOffset =
    props.mobileOffset ?? (onEditor && belowRail && position === "bottom-right" ? EDITOR_PHONE_OFFSET : undefined);

  return (
    <KitToaster
      variant="snackbar"
      // Every toast can be dismissed by hand (kit Toast spec; 07a/07c ×).
      closeButton
      {...props}
      theme={props.theme ?? resolvedTheme}
      labels={{ close: t("close"), ...labels, container: ariaLabel }}
      position={position}
      offset={offset}
      mobileOffset={mobileOffset}
      // Sonner's own layer is above everything; the editor's sits just under --z-modal.
      className={cn(props.className, onEditor && "z-[calc(var(--z-modal)-1)]!")}
    />
  );
};

export { Toaster };
