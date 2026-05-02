"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Clock,
  Timer,
  Cloud,
  TrendingUp,
  Trophy,
  Laugh,
  Wifi,
  Star,
  Waves,
  Rocket,
  LucideIcon,
} from "lucide-react";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WizardPluginConfig {
  date_time: { enabled: boolean; timezone: string };
  // Registry plugins to install-and-enable on proceed
  registry_selected: string[];
}

interface StepEasyPluginsProps {
  config: WizardPluginConfig;
  onConfigChange: (config: WizardPluginConfig) => void;
  onValidChange: (valid: boolean) => void;
}

// ---------------------------------------------------------------------------
// Curated pick list
// ---------------------------------------------------------------------------

interface CuratedPlugin {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  builtin: boolean;
  badge?: string;
}

const CURATED_PLUGINS: CuratedPlugin[] = [
  {
    id: "date_time",
    name: "Date & Time",
    description: "Display the current date and time on your board.",
    icon: Clock,
    builtin: true,
  },
  {
    id: "countdown",
    name: "Countdown",
    description: "Countdown timer to any date or event.",
    icon: Timer,
    builtin: true,
  },
  {
    id: "weather",
    name: "Weather",
    description: "Current conditions, temperature, and humidity.",
    icon: Cloud,
    builtin: false,
    badge: "Popular",
  },
  {
    id: "stocks",
    name: "Stock Prices",
    description: "Real-time stock prices and percentage changes.",
    icon: TrendingUp,
    builtin: false,
  },
  {
    id: "sports_scores",
    name: "Sports Scores",
    description: "Recent match scores for NFL, Soccer, NHL, and more.",
    icon: Trophy,
    builtin: false,
    badge: "Popular",
  },
  {
    id: "dad_jokes",
    name: "Dad Jokes",
    description: "Random dad jokes. No API key needed.",
    icon: Laugh,
    builtin: false,
    badge: "No setup",
  },
  {
    id: "guest_wifi",
    name: "Guest WiFi",
    description: "Display guest WiFi credentials on your board.",
    icon: Wifi,
    builtin: false,
    badge: "No setup",
  },
  {
    id: "star_trek_quotes",
    name: "Star Trek Quotes",
    description: "Wisdom from the Federation. No API key needed.",
    icon: Star,
    builtin: false,
    badge: "No setup",
  },
  {
    id: "surf",
    name: "Surf Conditions",
    description: "Wave height and swell period for your local break.",
    icon: Waves,
    builtin: false,
  },
  {
    id: "spacecraft_launches",
    name: "Spacecraft Launches",
    description: "Track upcoming launch countdowns and statuses.",
    icon: Rocket,
    builtin: false,
    badge: "No setup",
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StepEasyPlugins({
  config,
  onConfigChange,
  onValidChange,
}: StepEasyPluginsProps) {
  const t = useTranslations("wizard.easyPlugins");
  const [currentTime, setCurrentTime] = useState("");

  // This step is always valid (all choices are optional)
  useEffect(() => {
    onValidChange(true);
  }, [onValidChange]);

  // Live clock preview for timezone
  useEffect(() => {
    const updateTime = () => {
      try {
        setCurrentTime(
          new Date().toLocaleTimeString("en-US", {
            timeZone: config.date_time.timezone,
            hour: "numeric",
            minute: "2-digit",
            hour12: true,
          })
        );
      } catch {
        setCurrentTime("--:--");
      }
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, [config.date_time.timezone]);

  const isSelected = (id: string) => {
    if (id === "date_time") return config.date_time.enabled;
    if (id === "countdown") return config.registry_selected.includes("countdown");
    return config.registry_selected.includes(id);
  };

  const handleToggle = (plugin: CuratedPlugin, checked: boolean) => {
    if (plugin.id === "date_time") {
      onConfigChange({ ...config, date_time: { ...config.date_time, enabled: checked } });
      return;
    }
    const next = checked
      ? [...config.registry_selected.filter((x) => x !== plugin.id), plugin.id]
      : config.registry_selected.filter((x) => x !== plugin.id);
    onConfigChange({ ...config, registry_selected: next });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground mb-1">
        {t("description")}
      </p>
      <p className="text-xs text-muted-foreground mb-4">
        You can add more from the{" "}
        <Link href="/integrations" className="underline hover:text-foreground">
          Integrations
        </Link>{" "}
        page at any time.
      </p>

      <div className="space-y-3">
        {CURATED_PLUGINS.map((plugin) => {
          const Icon = plugin.icon;
          const selected = isSelected(plugin.id);
          return (
            <Card
              key={plugin.id}
              className={cn(
                "transition-all cursor-pointer select-none",
                selected && "ring-2 ring-primary"
              )}
              onClick={() => handleToggle(plugin, !selected)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "p-2 rounded-lg",
                        selected ? "bg-primary/10" : "bg-muted"
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-5 w-5",
                          selected ? "text-primary" : "text-muted-foreground"
                        )}
                      />
                    </div>
                    <div>
                      <CardTitle className="text-base flex items-center gap-2">
                        {plugin.name}
                        {plugin.badge && (
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                            {plugin.badge}
                          </Badge>
                        )}
                        {plugin.builtin && (
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 text-muted-foreground">
                            Built-in
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="text-xs">{plugin.description}</CardDescription>
                    </div>
                  </div>
                  <Switch
                    checked={selected}
                    onCheckedChange={(checked) => handleToggle(plugin, checked)}
                    onClick={(e) => e.stopPropagation()}
                    aria-label={`Toggle ${plugin.name}`}
                  />
                </div>
              </CardHeader>

              {/* Inline timezone picker for date_time */}
              {plugin.id === "date_time" && selected && (
                <CardContent className="pt-2 space-y-3" onClick={(e) => e.stopPropagation()}>
                  <div className="space-y-2">
                    <Label htmlFor="wizard-timezone" className="text-sm">{t("timezoneLabel")}</Label>
                    <TimezonePicker
                      id="wizard-timezone"
                      value={config.date_time.timezone}
                      onChange={(timezone) =>
                        onConfigChange({
                          ...config,
                          date_time: { ...config.date_time, timezone },
                        })
                      }
                    />
                  </div>
                  <div className="text-sm text-muted-foreground bg-muted/50 p-2 rounded">
                    Preview: <span className="font-mono">{currentTime}</span>
                  </div>
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
