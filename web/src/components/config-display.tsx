"use client";

import { Calendar, Cloud, Home, RotateCw, Wifi } from "lucide-react";
import type { ComponentType } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig } from "@/hooks/use-board";
import type { ServiceKey } from "@/hooks/use-config-overrides";
import { useConfigOverrides } from "@/hooks/use-config-overrides";

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

// Config item display with icon - use short labels for compact display
const configItems: Array<{ key: ServiceKey; label: string; icon: ComponentType<{ className?: string }> }> = [
  { key: "datetime_enabled" as ServiceKey, label: "Date", icon: Calendar },
  { key: "weather_enabled" as ServiceKey, label: "Weather", icon: Cloud },
  { key: "home_assistant_enabled" as ServiceKey, label: "Home", icon: Home },
  { key: "guest_wifi_enabled" as ServiceKey, label: "WiFi", icon: Wifi },
  { key: "star_trek_quotes_enabled" as ServiceKey, label: "Quotes", icon: VulcanSalute },
  { key: "rotation_enabled" as ServiceKey, label: "Rotation", icon: RotateCw },
];

export function ConfigDisplay() {
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
          <CardTitle className="text-lg">Configuration</CardTitle>
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
          Configuration
          <span className="text-xs font-normal text-muted-foreground">(click to toggle preview)</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-2">
          {configItems.map(({ key, label, icon: Icon }) => {
            const backendValue = (data?.[key] ?? false) as boolean;
            const enabled = getEffectiveValue(key, backendValue);
            const overridden = isOverridden(key);
            return (
              <button
                key={key}
                onClick={() => handleToggle(key)}
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
                  {enabled ? "On" : "Off"}
                </Badge>
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
