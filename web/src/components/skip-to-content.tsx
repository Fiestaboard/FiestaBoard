"use client";

import { SkipToContent as UISkipToContent } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";

export function SkipToContent() {
  const t = useTranslations("navigation");
  return <UISkipToContent label={t("skipToMainContent")} />;
}
