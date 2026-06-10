"use client";

import { CircleCheckIcon, InfoIcon, Loader2Icon, OctagonXIcon, TriangleAlertIcon } from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";

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

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      containerAriaLabel={ariaLabel}
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
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
