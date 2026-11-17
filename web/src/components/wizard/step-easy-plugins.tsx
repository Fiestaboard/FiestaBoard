"use client";

import { Grid, Stack, Text, ToggleCard } from "@fiestaboard/ui";
import type { LucideIcon } from "lucide-react";
import { Clock, Cloud, House, Puzzle, TrainFront, TrendingUp } from "lucide-react";
import { useEffect } from "react";

import { useTranslations } from "@/i18n/translations";

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
  { id: "weather", icon: Cloud, builtin: false, needsSetup: true },
  { id: "calendar_sub", icon: Clock, builtin: false, needsSetup: true },
  { id: "muni", icon: TrainFront, builtin: false, needsSetup: true },
  { id: "home_assistant", icon: House, builtin: false, needsSetup: true },
  { id: "stocks", icon: TrendingUp, builtin: false, needsSetup: true },
  { id: "later", icon: Puzzle, builtin: true },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StepEasyPlugins({ config, onConfigChange, onValidChange }: StepEasyPluginsProps) {
  const t = useTranslations("wizard.easyPlugins");
  useEffect(() => {
    onValidChange(true);
  }, [onValidChange]);

  const isSelected = (id: string) => {
    if (id === "later") return !config.date_time.enabled && config.registry_selected.length === 0;
    if (id === "date_time") return config.date_time.enabled;
    return config.registry_selected.includes(id);
  };

  const handleToggle = (plugin: CuratedPlugin, checked: boolean) => {
    if (plugin.id === "later") {
      onConfigChange({ ...config, date_time: { ...config.date_time, enabled: false }, registry_selected: [] });
      return;
    }
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
      <Grid cols="1" md="2" gap="3">
        {CURATED_PLUGINS.map((plugin) => {
          const Icon = plugin.icon;
          return (
            <ToggleCard
              key={plugin.id}
              pressed={isSelected(plugin.id)}
              onPressedChange={(checked) => handleToggle(plugin, checked)}
              icon={<Icon aria-hidden="true" />}
              title={t(`items.${plugin.id}.name`)}
              description={t(`items.${plugin.id}.description`)}
              className="min-h-20"
            />
          );
        })}
      </Grid>
      <Text size="sm" tone="muted">
        {t("selectedCount", { count: (config.date_time.enabled ? 1 : 0) + config.registry_selected.length })}
      </Text>
      <Text size="xs" tone="muted">
        {t("configureLaterHint")}
      </Text>
    </Stack>
  );
}
