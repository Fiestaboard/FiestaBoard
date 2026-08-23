"use client";

import { PageSection } from "@fiestaboard/ui";
import { Globe } from "lucide-react";

import { LanguageSelector } from "@/components/language-selector";
import { useTranslations } from "@/i18n/translations";

export function LanguageSettingsCard() {
  const t = useTranslations("profile");

  return (
    <PageSection icon={<Globe />} title={t("languageTitle")} description={t("languageDescription")}>
      <LanguageSelector />
    </PageSection>
  );
}
