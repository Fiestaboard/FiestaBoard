/**
 * The status banners' strings (slice 2.3) live in `statusBanners`, in every
 * locale, with the same placeholders. "Silence Schedule" is a CANON name and
 * stays in English everywhere.
 */
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

import { locales } from "@/i18n/config";

const messagesDir = path.resolve(__dirname, "../../messages");

function section(locale: string): Record<string, string> {
  const all = JSON.parse(fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8"));
  return all.statusBanners;
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
}

const en = section("en");
const enKeys = Object.keys(en).sort();
const nonEnglish = locales.filter((l) => l !== "en");

// Words that are the same in a translation on purpose ("Online", "Offline"
// and Dutch "is offline" are the local words too; the product name stays).
const SAME_ON_PURPOSE = new Set([
  "hubOnline",
  "hubRemote",
  "diagnostics",
  "hubUnreachable",
  "displayOfflineTitle",
  "offlineBadge",
  "hubVersion",
]);

describe("statusBanners messages", () => {
  it("uses the 07a copy in English", () => {
    expect(en.hubUnreachableTitle).toBe("Can't reach your hub at {host}");
    expect(en.silencedTitle).toBe("Silence Schedule until {time}");
    expect(en.displayOfflineDetail).toContain("Last connected {time}");
  });

  it("never says 'last seen' (CANON: last connected, last shown)", () => {
    for (const locale of locales) {
      expect(JSON.stringify(section(locale)).toLowerCase()).not.toContain("last seen");
    }
  });

  it.each(locales)("%s has exactly en's keys", (locale) => {
    expect(Object.keys(section(locale)).sort()).toEqual(enKeys);
  });

  it.each(nonEnglish)("%s keeps every placeholder", (locale) => {
    const translated = section(locale);
    for (const key of enKeys) {
      expect(placeholders(translated[key]), `${locale}.${key}`).toEqual(placeholders(en[key]));
    }
  });

  it.each(nonEnglish)("%s translates the sentences", (locale) => {
    const translated = section(locale);
    const untranslated = enKeys.filter((key) => !SAME_ON_PURPOSE.has(key) && translated[key] === en[key]);
    expect(untranslated).toEqual([]);
  });

  it("is the one home of the hub-line words: navigation.hub is gone from every locale", () => {
    for (const locale of locales) {
      const all = JSON.parse(fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8"));
      expect(all.navigation.hub, locale).toBeUndefined();
      expect(section(locale).hubVersion, locale).toContain("{version}");
    }
  });

  it("uses the codebase's straight apostrophe in the English hub words", () => {
    expect(en.hubUnreachable).toBe("Can't reach");
  });

  it.each(locales)("%s keeps '{seconds} s' on one line (no-break space)", (locale) => {
    for (const key of ["hubUnreachableDetail", "hubUnreachableDetailNever"]) {
      expect(section(locale)[key], `${locale}.${key}`).not.toMatch(/\{seconds\} /);
    }
  });

  it.each(nonEnglish)("%s keeps the CANON name Silence Schedule", (locale) => {
    expect(section(locale).silencedTitle).toContain("Silence Schedule");
  });
});
