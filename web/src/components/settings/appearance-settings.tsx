"use client";

import { SegmentedControl, SegmentedControlItem } from "@fiestaboard/ui";
import { Monitor, Moon, Sun } from "lucide-react";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";

const THEMES = [
  { value: "light", Icon: Sun },
  { value: "dark", Icon: Moon },
  { value: "system", Icon: Monitor },
] as const;

type ThemeValue = (typeof THEMES)[number]["value"];

function isThemeValue(value: string): value is ThemeValue {
  return THEMES.some((option) => option.value === value);
}

export function AppearanceSettings() {
  const t = useTranslations("profile");
  const tPanels = useTranslations("settings.panels");
  const { theme, setTheme } = useTheme();
  const labels: Record<ThemeValue, string> = {
    light: t("lightMode"),
    dark: t("darkMode"),
    system: t("systemMode"),
  };

  return (
    <SettingsPanel icon={<Sun />} title={tPanels("theme")} description={tPanels("browserTheme")}>
      {/* One-of-three, so a radiogroup rather than three independent
          `aria-pressed` buttons: one tab stop, arrow keys move the choice,
          and the selected tile announces its position in the set. */}
      <SegmentedControl
        size="md"
        value={theme}
        onValueChange={(value) => {
          if (isThemeValue(value)) setTheme(value);
        }}
        aria-label={t("appearanceTitle")}
        className="max-w-sm"
      >
        {THEMES.map(({ value, Icon }) => (
          <SegmentedControlItem key={value} value={value} className="min-h-12">
            <Icon className="size-4" aria-hidden="true" />
            {labels[value]}
          </SegmentedControlItem>
        ))}
      </SegmentedControl>
    </SettingsPanel>
  );
}
