"use client";

import { useTranslations } from "@/i18n/translations";

export function SkipToContent() {
  const t = useTranslations("navigation");
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[200] focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-ring"
    >
      {t("skipToMainContent")}
    </a>
  );
}
