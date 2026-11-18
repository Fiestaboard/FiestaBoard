"use client";

import { Globe } from "lucide-react";

import { LanguageSelector } from "@/components/language-selector";
import { SettingsPanel } from "@/components/settings/settings-panel";
import { useTranslations } from "@/i18n/translations";

export function LanguageSettingsCard() {
  const t = useTranslations("profile");
  const tPanels = useTranslations("settings.panels");

  return (
    <SettingsPanel id="language" icon={<Globe />} title={t("languageTitle")} description={tPanels("browserTheme")}>
      <LanguageSelector />
    </SettingsPanel>
  );
}
