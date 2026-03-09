export const locales = ["en", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "sv", "tr", "ja", "ko", "zh"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

export const localeNames: Record<Locale, string> = {
  en: "English",
  es: "Español",
  fr: "Français",
  de: "Deutsch",
  it: "Italiano",
  pt: "Português",
  nl: "Nederlands",
  pl: "Polski",
  ru: "Русский",
  sv: "Svenska",
  tr: "Türkçe",
  ja: "日本語",
  ko: "한국어",
  zh: "简体中文",
};
