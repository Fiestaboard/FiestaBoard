/**
 * react-i18next initialization for FiestaBoard.
 *
 * Locale is detected at boot in the browser via
 * `i18next-browser-languagedetector` — cookie name is `NEXT_LOCALE`
 * for back-compat with users who already had a locale set before the
 * RR7 migration.
 *
 * All 14 locales are statically imported so they're available
 * synchronously at first render — there's no `Suspense` boundary
 * around the first message lookup. If bundle size becomes an issue we
 * can switch to dynamic imports + i18next's resource lazy-loading.
 */
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import de from "../../messages/de.json";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import fr from "../../messages/fr.json";
import it from "../../messages/it.json";
import ja from "../../messages/ja.json";
import ko from "../../messages/ko.json";
import nl from "../../messages/nl.json";
import pl from "../../messages/pl.json";
import pt from "../../messages/pt.json";
import ru from "../../messages/ru.json";
import sv from "../../messages/sv.json";
import tr from "../../messages/tr.json";
import zh from "../../messages/zh.json";
import { defaultLocale, locales } from "./config";

const resources = {
  en: { translation: en },
  es: { translation: es },
  fr: { translation: fr },
  de: { translation: de },
  it: { translation: it },
  pt: { translation: pt },
  nl: { translation: nl },
  pl: { translation: pl },
  ru: { translation: ru },
  sv: { translation: sv },
  tr: { translation: tr },
  ja: { translation: ja },
  ko: { translation: ko },
  zh: { translation: zh },
};

if (!i18n.isInitialized) {
  i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources,
      supportedLngs: [...locales],
      fallbackLng: defaultLocale,
      // We do our own ICU plural / placeholder interpolation in
      // `@/i18n/translations` because the existing message strings use
      // next-intl-style ICU syntax. Set i18next's interpolation prefix
      // to `{{` (not the default `{`) so its replacement pass doesn't
      // double-process our `{name}` placeholders.
      interpolation: { escapeValue: false, prefix: "{{", suffix: "}}" },
      detection: {
        order: ["cookie", "navigator", "htmlTag"],
        lookupCookie: "NEXT_LOCALE",
        caches: ["cookie"],
        cookieMinutes: 60 * 24 * 365,
      },
      returnNull: false,
      react: { useSuspense: false },
    });
}

export default i18n;
