"use client";

import { Badge, Card, CardContent, CardHeader, CardTitle, Skeleton } from "@fiestaboard/ui";
import { Calendar, Cloud, Home, RotateCw, Wifi } from "lucide-react";
import type { ComponentType } from "react";

import { useConfig } from "@/hooks/use-board";
import type { ServiceKey } from "@/hooks/use-config-overrides";
import { useConfigOverrides } from "@/hooks/use-config-overrides";
import { useTranslations } from "@/i18n/translations";

// Vulcan salute component - uses emoji with CSS filter to match icon theme
// Converts emoji to grayscale so it matches the monochrome icon style
const VulcanSalute = ({ className }: { className?: string }) => {
  // Check if it should be primary (enabled) or muted (disabled)
  const _isPrimary = className?.includes("text-primary");
  const isMuted = className?.includes("text-muted-foreground");

  // Apply grayscale filter to remove yellow color and match icon style
  // Use brightness to match the theme
  const filter = isMuted
    ? "grayscale(100%) brightness(0.6)" // Dimmer for muted state
    : "grayscale(100%) brightness(0)"; // Black for primary/enabled state

  return (
    <span
      aria-hidden="true"
      className={className}
      style={{
        fontSize: "1rem",
        lineHeight: "1rem",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "1rem",
        height: "1rem",
        filter: filter,
        color: "currentColor",
        textShadow: "none",
        WebkitFontSmoothing: "antialiased",
        MozOsxFontSmoothing: "grayscale",
      }}
    >
      🖖
    </span>
  );
};

// Config item display with icon - use short labels for compact display.
// `labelKey` maps to the `configDisplay.items.*` i18n keys.
const configItems: Array<{
  key: ServiceKey;
  labelKey: "date" | "weather" | "home" | "wifi" | "quotes" | "rotation";
  icon: ComponentType<{ className?: string }>;
}> = [
  { key: "datetime_enabled" as ServiceKey, labelKey: "date", icon: Calendar },
  { key: "weather_enabled" as ServiceKey, labelKey: "weather", icon: Cloud },
  { key: "home_assistant_enabled" as ServiceKey, labelKey: "home", icon: Home },
  { key: "guest_wifi_enabled" as ServiceKey, labelKey: "wifi", icon: Wifi },
  { key: "star_trek_quotes_enabled" as ServiceKey, labelKey: "quotes", icon: VulcanSalute },
  { key: "rotation_enabled" as ServiceKey, labelKey: "rotation", icon: RotateCw },
];

export function ConfigDisplay() {
  const t = useTranslations("configDisplay");
  const { data, isLoading } = useConfig();
  const { overrides, setOverride, getEffectiveValue, isOverridden } = useConfigOverrides();

  const handleToggle = (key: ServiceKey) => {
    const backendValue = (data?.[key] ?? false) as boolean;
    const currentOverride = overrides[key];

    // Cycle through: backend value -> opposite -> back to backend
    if (currentOverride === null) {
      // First click: toggle to opposite of backend
      setOverride(key, !backendValue);
    } else {
      // Second click: back to backend value (null)
      setOverride(key, null);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{t("title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          {t("title")}
          <span className="text-xs font-normal text-muted-foreground">({t("clickToToggle")})</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-2">
          {configItems.map(({ key, labelKey, icon: Icon }) => {
            const backendValue = (data?.[key] ?? false) as boolean;
            const enabled = getEffectiveValue(key, backendValue);
            const overridden = isOverridden(key);
            const label = t(`items.${labelKey}`);
            return (
              <button
                key={key}
                onClick={() => handleToggle(key)}
                aria-pressed={enabled}
                aria-label={t("toggleServiceAriaLabel", { name: label })}
                className={`flex items-center gap-2 p-2 rounded-md border transition-all duration-200 ${
                  enabled
                    ? "bg-primary/10 border-primary/30 hover:bg-primary/15"
                    : "bg-muted/50 border-transparent hover:bg-muted/70"
                } ${overridden ? "ring-2 ring-offset-1 ring-warning/50" : ""}`}
              >
                <Icon
                  className={`h-4 w-4 shrink-0 transition-colors ${enabled ? "text-primary" : "text-muted-foreground"}`}
                />
                <span
                  className={`text-xs truncate transition-colors ${
                    enabled ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {label}
                </span>
                <Badge
                  variant={enabled ? "default" : "secondary"}
                  className={`ml-auto shrink-0 text-[10px] px-1.5 py-0.5 transition-all ${
                    enabled ? "bg-fiesta-green hover:bg-fiesta-green" : ""
                  }`}
                >
                  {enabled ? t("on") : t("off")}
                </Badge>
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
