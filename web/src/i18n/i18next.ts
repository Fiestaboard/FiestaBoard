/**
 * react-i18next initialization for FiestaBoard.
 *
 * Locale is detected at boot in the browser via
 * `i18next-browser-languagedetector` — cookie name is `NEXT_LOCALE`
 * for back-compat with users who already had a locale set before the
 * RR7 migration.
 *
 * English is bundled so the first render can always resolve a message.
 * The other 13 locales are separate chunks fetched on demand by the
 * backend below: bundling all 14 put ~1.8 MB of translation JSON in the
 * critical-path chunk, which every visitor downloaded (and the Pi
 * gzipped on the fly) after each nightly update. `i18nReady` resolves
 * once the detected locale is loaded; the client entry waits on it
 * before hydrating, so a non-English visitor never sees raw keys.
 */
import i18n, { type BackendModule, type ResourceKey } from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "../../messages/en.json";
import { defaultLocale, locales } from "./config";

const lazyLocales = import.meta.glob<{ default: ResourceKey }>(["../../messages/*.json", "!../../messages/en.json"]);

/** Loads a non-English locale's messages from its own chunk. */
export const lazyLocaleBackend: BackendModule = {
  type: "backend",
  init() {},
  read(language, _namespace, callback) {
    if (language === defaultLocale) {
      callback(null, en);
      return;
    }
    const load = lazyLocales[`../../messages/${language}.json`];
    if (!load) {
      callback(new Error(`No messages for locale "${language}"`), false);
      return;
    }
    load().then(
      (module) => callback(null, module.default),
      (error: unknown) => callback(error instanceof Error ? error : new Error(String(error)), false),
    );
  },
};

let ready: Promise<unknown> = Promise.resolve();

if (!i18n.isInitialized) {
  ready = i18n
    .use(lazyLocaleBackend)
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources: { en: { translation: en } },
      // Keep the bundled `en` and fetch every other locale through the backend.
      partialBundledLanguages: true,
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

export const i18nReady = ready;

export default i18n;
