"use client";

import { Globe } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { type Locale, localeNames, locales } from "@/i18n/config";
import i18n from "@/i18n/i18next";

function setLocaleCookie(locale: Locale) {
  document.cookie = `NEXT_LOCALE=${locale};path=/;max-age=${60 * 60 * 24 * 365};SameSite=Lax`;
}

export function LanguageSelector() {
  const locale = useLocale();
  const [isPending, startTransition] = useTransition();
  const t = useTranslations("common");

  function handleChange(value: string) {
    const newLocale = value as Locale;
    setLocaleCookie(newLocale);
    startTransition(() => {
      // SPA-mode: i18next's language-detector reads the cookie only at
      // boot, so we have to push the change into i18next ourselves for
      // the UI to re-render. The cookie write above keeps the choice
      // sticky across reloads.
      void i18n.changeLanguage(newLocale);
    });
  }

  return (
    <Select value={locale} onValueChange={handleChange} disabled={isPending}>
      <SelectTrigger className="h-8 w-[130px] text-xs gap-1" aria-label={t("language")}>
        <Globe className="h-3.5 w-3.5 flex-shrink-0" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {locales.map((loc) => (
          <SelectItem key={loc} value={loc} className="text-xs">
            {localeNames[loc]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
