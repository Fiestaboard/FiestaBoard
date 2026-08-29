"use client";

import { PageSection, ToggleCard, ToggleCardGroup } from "@fiestaboard/ui";
import { Monitor, Moon, Sun } from "lucide-react";

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
  const { theme, setTheme } = useTheme();
  const labels: Record<ThemeValue, string> = {
    light: t("lightMode"),
    dark: t("darkMode"),
    system: t("systemMode"),
  };

  return (
    <PageSection icon={<Sun />} title={t("appearanceTitle")} description={t("appearanceDescription")}>
      {/* One-of-three, so a radiogroup rather than three independent
          `aria-pressed` buttons: one tab stop, arrow keys move the choice,
          and the selected tile announces its position in the set. */}
      <ToggleCardGroup
        columns="3"
        align="center"
        value={theme}
        onValueChange={(value) => {
          if (isThemeValue(value)) setTheme(value);
        }}
        aria-label={t("appearanceTitle")}
        className="max-w-sm"
      >
        {THEMES.map(({ value, Icon }) => (
          <ToggleCard key={value} value={value} icon={<Icon className="size-5" />} title={labels[value]} />
        ))}
      </ToggleCardGroup>
    </PageSection>
  );
}
