/**
 * The out-of-sync banner's strings (issue #1945) live in their own
 * `boardOutOfSync` namespace, translated in every locale. PR #2251 shipped its
 * strings in `activeDisplay` as English in all 13 other locales; this keeps
 * that from coming back: same key set everywhere, no English left in a
 * translation, the same placeholders, and none of the moved keys still in
 * `activeDisplay`.
 */
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

import { locales } from "@/i18n/config";

type Messages = Record<string, Record<string, unknown>>;

const messagesDir = path.resolve(__dirname, "../../messages");

function load(locale: string): Messages {
  return JSON.parse(fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8"));
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
}

const en = load("en");
const enSection = (en.boardOutOfSync ?? {}) as Record<string, string>;
const enKeys = Object.keys(enSection).sort();
const nonEnglish = locales.filter((l) => l !== "en");

const MOVED_FROM_ACTIVE_DISPLAY = [
  "updatedExternally",
  "resendToBoard",
  "toastResendSuccess",
  "toastResendFailed",
  "saveAsPage",
  "externalPageName",
  "toastSaveAsPageSuccess",
  "toastSaveAsPageFailed",
];

describe("boardOutOfSync messages", () => {
  it("defines the banner's 19 strings in English", () => {
    expect(enKeys).toHaveLength(19);
    expect(enSection.title).toBe("Another app changed this board");
  });

  it.each(locales)("%s has exactly en's boardOutOfSync keys", (locale) => {
    const section = load(locale).boardOutOfSync as Record<string, string> | undefined;
    expect(section, `${locale}.json has no boardOutOfSync namespace`).toBeDefined();
    expect(Object.keys(section!).sort()).toEqual(enKeys);
  });

  it.each(nonEnglish)("%s translates every boardOutOfSync string", (locale) => {
    const section = load(locale).boardOutOfSync as Record<string, string>;
    const untranslated = enKeys.filter((key) => section[key] === enSection[key]);
    expect(untranslated).toEqual([]);
  });

  it.each(locales)("%s keeps en's placeholders in every boardOutOfSync string", (locale) => {
    const section = load(locale).boardOutOfSync as Record<string, string>;
    for (const key of enKeys) {
      expect(placeholders(section[key]), `${locale}.boardOutOfSync.${key}`).toEqual(placeholders(enSection[key]));
    }
  });

  it.each(locales)("%s no longer carries the moved keys in activeDisplay", (locale) => {
    const activeDisplay = load(locale).activeDisplay as Record<string, unknown>;
    const leftovers = MOVED_FROM_ACTIVE_DISPLAY.filter((key) => key in activeDisplay);
    expect(leftovers).toEqual([]);
  });
});
