import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { locales, type Locale } from "@/i18n/config";
import i18n, { i18nReady } from "@/i18n/i18next";
import { useTranslations } from "@/i18n/translations";

// The shared setup substitutes an English-only hook. These regressions must
// exercise the real hook, locale resources, and ICU interpolation together.
vi.unmock("@/i18n/translations");

const counts = [0, 1, 2, 5, 21, 22] as const;
const ruleCounts = {
  en: [
    "0 rules + default",
    "1 rule + default",
    "2 rules + default",
    "5 rules + default",
    "21 rules + default",
    "22 rules + default",
  ],
  es: [
    "0 reglas + predeterminada",
    "1 regla + predeterminada",
    "2 reglas + predeterminada",
    "5 reglas + predeterminada",
    "21 reglas + predeterminada",
    "22 reglas + predeterminada",
  ],
  fr: [
    "0 règle + page par défaut",
    "1 règle + page par défaut",
    "2 règles + page par défaut",
    "5 règles + page par défaut",
    "21 règles + page par défaut",
    "22 règles + page par défaut",
  ],
  de: [
    "0 Regeln + Standardseite",
    "1 Regel + Standardseite",
    "2 Regeln + Standardseite",
    "5 Regeln + Standardseite",
    "21 Regeln + Standardseite",
    "22 Regeln + Standardseite",
  ],
  it: [
    "0 regole + predefinita",
    "1 regola + predefinita",
    "2 regole + predefinita",
    "5 regole + predefinita",
    "21 regole + predefinita",
    "22 regole + predefinita",
  ],
  pt: [
    "0 regra + padrão",
    "1 regra + padrão",
    "2 regras + padrão",
    "5 regras + padrão",
    "21 regras + padrão",
    "22 regras + padrão",
  ],
  nl: [
    "0 regels + standaardpagina",
    "1 regel + standaardpagina",
    "2 regels + standaardpagina",
    "5 regels + standaardpagina",
    "21 regels + standaardpagina",
    "22 regels + standaardpagina",
  ],
  pl: [
    "0 reguł + domyślna",
    "1 reguła + domyślna",
    "2 reguły + domyślna",
    "5 reguł + domyślna",
    "21 reguł + domyślna",
    "22 reguły + domyślna",
  ],
  ru: [
    "0 правил + страница по умолчанию",
    "1 правило + страница по умолчанию",
    "2 правила + страница по умолчанию",
    "5 правил + страница по умолчанию",
    "21 правило + страница по умолчанию",
    "22 правила + страница по умолчанию",
  ],
  sv: [
    "0 regler + standardsida",
    "1 regel + standardsida",
    "2 regler + standardsida",
    "5 regler + standardsida",
    "21 regler + standardsida",
    "22 regler + standardsida",
  ],
  tr: [
    "0 kural + varsayılan",
    "1 kural + varsayılan",
    "2 kural + varsayılan",
    "5 kural + varsayılan",
    "21 kural + varsayılan",
    "22 kural + varsayılan",
  ],
  ja: [
    "0件のルール + デフォルト",
    "1件のルール + デフォルト",
    "2件のルール + デフォルト",
    "5件のルール + デフォルト",
    "21件のルール + デフォルト",
    "22件のルール + デフォルト",
  ],
  ko: [
    "규칙 0개 + 기본 페이지",
    "규칙 1개 + 기본 페이지",
    "규칙 2개 + 기본 페이지",
    "규칙 5개 + 기본 페이지",
    "규칙 21개 + 기본 페이지",
    "규칙 22개 + 기본 페이지",
  ],
  zh: [
    "0 条规则 + 默认页面",
    "1 条规则 + 默认页面",
    "2 条规则 + 默认页面",
    "5 条规则 + 默认页面",
    "21 条规则 + 默认页面",
    "22 条规则 + 默认页面",
  ],
} satisfies Record<Locale, readonly string[]>;

beforeAll(async () => {
  await i18nReady;
});

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
});

describe("collection rule counts through the real translation hook", () => {
  it.each(
    locales.flatMap((locale) => counts.map((count, index) => ({ locale, count, expected: ruleCounts[locale][index] }))),
  )("$locale formats $count rules with its locale's plural form", async ({ locale, count, expected }) => {
    await i18n.changeLanguage(locale);
    const { result } = renderHook(() => useTranslations("collections"));

    expect(result.current("ruleCount", { count })).toBe(expected);
  });

  it("updates a mounted hook's plural rules when the language changes", async () => {
    await i18n.changeLanguage("en");
    const { result } = renderHook(() => useTranslations("collections"));
    expect(result.current("ruleCount", { count: 2 })).toBe("2 rules + default");

    await act(async () => {
      await i18n.changeLanguage("pl");
    });

    expect(result.current("ruleCount", { count: 2 })).toBe("2 reguły + domyślna");
  });
});

describe("ICU plural branch selection through the real translation hook", () => {
  it.each([
    { count: 0, expected: "exact zero" },
    { count: 1, expected: "exact one" },
    { count: 2, expected: "exact two" },
    { count: 5, expected: "many 5" },
  ])("prefers exact branches before Polish categories for $count", async ({ count, expected }) => {
    await i18n.changeLanguage("pl");
    i18n.addResource(
      "pl",
      "translation",
      "pluralRegression.exact",
      "{count, plural, one {one #} few {few #} many {many #} other {other #} =0 {exact zero} =1 {exact one} =2 {exact two}}",
    );
    const { result } = renderHook(() => useTranslations("pluralRegression"));

    expect(result.current("exact", { count })).toBe(expected);
  });

  it("falls back to other when the selected locale category has no branch", async () => {
    await i18n.changeLanguage("ru");
    i18n.addResource(
      "ru",
      "translation",
      "pluralRegression.fallback",
      "{count, plural, one {one #} other {fallback #}}",
    );
    const { result } = renderHook(() => useTranslations("pluralRegression"));

    expect(result.current("fallback", { count: 2 })).toBe("fallback 2");
  });

  it("preserves an intentionally empty category branch", async () => {
    await i18n.changeLanguage("en");
    i18n.addResource("en", "translation", "pluralRegression.empty", "{count, plural, one {} other {other #}}");
    const { result } = renderHook(() => useTranslations("pluralRegression"));

    expect(result.current("empty", { count: 1 })).toBe("");
  });

  it.each([
    { locale: "ru", count: 21, expected: "21 rules" },
    { locale: "pt", count: 0, expected: "0 rules" },
  ])("uses English plural categories for an English fallback in $locale", async ({ locale, count, expected }) => {
    await i18n.changeLanguage(locale);
    i18n.addResource(
      "en",
      "translation",
      "pluralRegression.englishOnly",
      "{count, plural, one {# rule} other {# rules}}",
    );
    const { result } = renderHook(() => useTranslations("pluralRegression"));

    expect(result.current("englishOnly", { count })).toBe(expected);
  });
});
