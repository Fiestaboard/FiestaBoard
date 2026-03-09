import { describe, it, expect } from "vitest";
import { locales, defaultLocale, localeNames, type Locale } from "@/i18n/config";
import fs from "fs";
import path from "path";

describe("i18n config", () => {
  it("exports 14 locales", () => {
    expect(locales).toHaveLength(14);
  });

  it("has English as the default locale", () => {
    expect(defaultLocale).toBe("en");
  });

  it("every locale has a display name", () => {
    for (const locale of locales) {
      expect(localeNames[locale]).toBeDefined();
      expect(localeNames[locale].length).toBeGreaterThan(0);
    }
  });

  it("includes the expected language set", () => {
    const expected = ["en", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "sv", "tr", "ja", "ko", "zh"];
    expect([...locales]).toEqual(expected);
  });
});

describe("translation files", () => {
  const messagesDir = path.resolve(__dirname, "../../messages");
  const enMessages = JSON.parse(
    fs.readFileSync(path.join(messagesDir, "en.json"), "utf-8")
  );
  const enNamespaces = Object.keys(enMessages).sort();
  const enKeyCount = countKeys(enMessages);

  function countKeys(obj: Record<string, unknown>): number {
    let count = 0;
    for (const value of Object.values(obj)) {
      if (typeof value === "object" && value !== null) {
        count += countKeys(value as Record<string, unknown>);
      } else {
        count++;
      }
    }
    return count;
  }

  function getLeafKeys(obj: Record<string, unknown>, prefix = ""): string[] {
    const keys: string[] = [];
    for (const [key, value] of Object.entries(obj)) {
      const fullKey = prefix ? `${prefix}.${key}` : key;
      if (typeof value === "object" && value !== null) {
        keys.push(...getLeafKeys(value as Record<string, unknown>, fullKey));
      } else {
        keys.push(fullKey);
      }
    }
    return keys.sort();
  }

  it("a JSON file exists for every configured locale", () => {
    for (const locale of locales) {
      const filePath = path.join(messagesDir, `${locale}.json`);
      expect(fs.existsSync(filePath), `Missing ${locale}.json`).toBe(true);
    }
  });

  it("every locale file is valid JSON", () => {
    for (const locale of locales) {
      const filePath = path.join(messagesDir, `${locale}.json`);
      expect(() => JSON.parse(fs.readFileSync(filePath, "utf-8"))).not.toThrow();
    }
  });

  it("every locale has the same top-level namespaces as English", () => {
    for (const locale of locales) {
      if (locale === "en") continue;
      const messages = JSON.parse(
        fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8")
      );
      const namespaces = Object.keys(messages).sort();
      expect(namespaces, `${locale} namespace mismatch`).toEqual(enNamespaces);
    }
  });

  it("every locale has the same number of leaf keys as English", () => {
    for (const locale of locales) {
      if (locale === "en") continue;
      const messages = JSON.parse(
        fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8")
      );
      const localKeyCount = countKeys(messages);
      expect(
        localKeyCount,
        `${locale} has ${localKeyCount} keys, English has ${enKeyCount}`
      ).toBe(enKeyCount);
    }
  });

  it("every locale has exactly the same key paths as English", () => {
    const enKeys = getLeafKeys(enMessages);

    for (const locale of locales) {
      if (locale === "en") continue;
      const messages = JSON.parse(
        fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8")
      );
      const localeKeys = getLeafKeys(messages);

      const missingInLocale = enKeys.filter((k) => !localeKeys.includes(k));
      const extraInLocale = localeKeys.filter((k) => !enKeys.includes(k));

      expect(
        missingInLocale,
        `${locale} is missing keys: ${missingInLocale.join(", ")}`
      ).toEqual([]);
      expect(
        extraInLocale,
        `${locale} has extra keys: ${extraInLocale.join(", ")}`
      ).toEqual([]);
    }
  });

  it("no translation value is empty string", () => {
    for (const locale of locales) {
      const messages = JSON.parse(
        fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8")
      );
      const keys = getLeafKeys(messages);
      for (const key of keys) {
        const parts = key.split(".");
        let current: unknown = messages;
        for (const part of parts) {
          current = (current as Record<string, unknown>)[part];
        }
        expect(
          current,
          `${locale}: key "${key}" is empty`
        ).not.toBe("");
      }
    }
  });
});
