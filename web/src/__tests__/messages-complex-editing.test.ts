/**
 * Slice 2.9's strings live in `complexEditing`, in every locale, with the
 * same keys and placeholders as English.
 */
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

import { locales } from "@/i18n/config";

const messagesDir = path.resolve(__dirname, "../../messages");

function section(locale: string): Record<string, string> {
  const all = JSON.parse(fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8"));
  return all.complexEditing;
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
}

const en = section("en");

describe("complexEditing messages", () => {
  it.each(locales)("%s has every key with the same placeholders", (locale) => {
    const messages = section(locale);
    expect(Object.keys(messages).sort()).toEqual(Object.keys(en).sort());
    for (const key of Object.keys(en)) {
      expect(placeholders(messages[key]), `${locale}.${key}`).toEqual(placeholders(en[key]));
      expect(messages[key].trim(), `${locale}.${key}`).not.toBe("");
    }
  });
});
