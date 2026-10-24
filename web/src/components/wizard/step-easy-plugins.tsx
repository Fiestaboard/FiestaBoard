"use client";

import {
  Badge,
  Box,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Label,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import type { LucideIcon } from "lucide-react";
import { Clock, Cloud, Laugh, Rocket, Star, Timer, TrendingUp, Trophy, Waves, Wifi } from "lucide-react";
import { useEffect, useState } from "react";

import { TimezonePicker } from "@/components/ui/timezone-picker";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

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
  icon: LucideIcon;
  builtin: boolean;
  needsSetup?: boolean;
}

const CURATED_PLUGINS: CuratedPlugin[] = [
  {
    id: "date_time",
    icon: Clock,
    builtin: true,
  },
  {
    id: "countdown",
    needsSetup: true,
    icon: Timer,
    builtin: true,
  },
  {
    id: "weather",
    needsSetup: true,
    icon: Cloud,
    builtin: false,
  },
  {
    id: "stocks",
    needsSetup: true,
    icon: TrendingUp,
    builtin: false,
  },
  {
    id: "sports_scores",
    needsSetup: true,
    icon: Trophy,
    builtin: false,
  },
  {
    id: "dad_jokes",
    icon: Laugh,
    builtin: false,
  },
  {
    id: "guest_wifi",
    needsSetup: true,
    icon: Wifi,
    builtin: false,
  },
  {
    id: "star_trek_quotes",
    icon: Star,
    builtin: false,
  },
  {
    id: "surf",
    needsSetup: true,
    icon: Waves,
    builtin: false,
  },
  {
    id: "spacecraft_launches",
    icon: Rocket,
    builtin: false,
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StepEasyPlugins({ config, onConfigChange, onValidChange }: StepEasyPluginsProps) {
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
          new Date().toLocaleTimeString(undefined, {
            timeZone: config.date_time.timezone,
            hour: "numeric",
            minute: "2-digit",
            hour12: true,
          }),
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
    <Stack gap="4">
      <Text tone="muted" className="mb-1">
        {t("optionalDescription")}
      </Text>
      <Text size="xs" tone="muted" className="mb-4">
        {t("configureLaterHint")}
      </Text>

      <Stack gap="3">
        {CURATED_PLUGINS.map((plugin) => {
          const Icon = plugin.icon;
          const selected = isSelected(plugin.id);
          return (
            <Card
              key={plugin.id}
              className={cn("transition-all cursor-pointer select-none", selected && "ring-2 ring-primary")}
              onClick={() => handleToggle(plugin, !selected)}
            >
              <CardHeader className="pb-2">
                <Flex align="center" justify="between">
                  <Flex align="center" gap="3">
                    <Box className={cn("p-2 rounded-lg", selected ? "bg-primary/10" : "bg-muted")}>
                      <Icon className={cn("h-5 w-5", selected ? "text-primary" : "text-muted-foreground")} />
                    </Box>
                    <Box>
                      <CardTitle className="text-base flex flex-wrap items-center gap-2">
                        {t(`items.${plugin.id}.name`)}
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                          {t(plugin.needsSetup ? "configureBadge" : "readyBadge")}
                        </Badge>
                        {plugin.builtin && (
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 text-muted-foreground">
                            {t("builtInBadge")}
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="text-xs">{t(`items.${plugin.id}.description`)}</CardDescription>
                    </Box>
                  </Flex>
                  <Switch
                    checked={selected}
                    onCheckedChange={(checked) => handleToggle(plugin, checked)}
                    onClick={(e) => e.stopPropagation()}
                    aria-label={t("toggleLabel", { name: t(`items.${plugin.id}.name`) })}
                  />
                </Flex>
              </CardHeader>

              {/* Inline timezone picker for date_time */}
              {plugin.id === "date_time" && selected && (
                <CardContent className="pt-2 space-y-3" onClick={(e) => e.stopPropagation()}>
                  <Stack gap="2">
                    <Label htmlFor="wizard-timezone" className="text-sm">
                      {t("timezoneLabel")}
                    </Label>
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
                  </Stack>
                  <Text tone="muted" className="bg-muted/50 p-2 rounded">
                    {t("previewLabel")}{" "}
                    <Text as="span" tone="muted" className="font-mono">
                      {currentTime}
                    </Text>
                  </Text>
                </CardContent>
              )}
            </Card>
          );
        })}
      </Stack>
    </Stack>
  );
}
