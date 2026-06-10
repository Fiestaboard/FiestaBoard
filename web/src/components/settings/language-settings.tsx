"use client";

import { Globe } from "lucide-react";

import { LanguageSelector } from "@/components/language-selector";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useTranslations } from "@/i18n/translations";

export function LanguageSettingsCard() {
  const t = useTranslations("profile");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="h-4 w-4" />
          {t("languageTitle")}
        </CardTitle>
        <CardDescription>{t("languageDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        <LanguageSelector />
      </CardContent>
    </Card>
  );
}
