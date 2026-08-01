"use client";

import { ThemeToggle as UIThemeToggle } from "@fiestaboard/ui";

import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const t = useTranslations("themeToggle");

  return (
    <UIThemeToggle
      theme={theme === "dark" ? "dark" : "light"}
      onToggle={() => setTheme(theme === "dark" ? "light" : "dark")}
      label={t("toggleTheme")}
    />
  );
}
