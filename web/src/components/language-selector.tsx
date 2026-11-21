"use client";

import { Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Stack } from "@fiestaboard/ui";
import { useId, useTransition } from "react";

import { type Locale, localeNames, locales } from "@/i18n/config";
import i18n from "@/i18n/i18next";
import { useLocale, useTranslations } from "@/i18n/translations";

function setLocaleCookie(locale: Locale) {
  document.cookie = `NEXT_LOCALE=${locale};path=/;max-age=${60 * 60 * 24 * 365};SameSite=Lax`;
}

/**
 * The Language field of Settings › Language & time (07e `320:6520`): a field
 * label and a full-width Select, like the Time zone field under it. Not the
 * kit's LanguageSelector chip — that 130×32 globe control is the docs-site
 * header's (Figma `26:790`), not a settings field (BB-FS-9).
 */
export function LanguageSelector() {
  const locale = useLocale();
  const [isPending, startTransition] = useTransition();
  const t = useTranslations("common");
  const id = useId();

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
    <Stack gap="2">
      <Label htmlFor={id} className="text-sm font-medium">
        {t("language")}
      </Label>
      <Select value={locale} onValueChange={(value) => handleChange(value as string)} disabled={isPending}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {locales.map((loc) => (
            <SelectItem key={loc} value={loc}>
              {localeNames[loc]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Stack>
  );
}
