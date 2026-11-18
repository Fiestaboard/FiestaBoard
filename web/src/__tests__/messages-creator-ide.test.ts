/**
 * The Creator IDE's strings (slice 2.11) live in `creatorIde`, in every
 * locale, with the same keys and the same {placeholders}.
 */
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

import { locales } from "@/i18n/config";

const messagesDir = path.resolve(__dirname, "../../messages");

function flatten(value: unknown, prefix = ""): Record<string, string> {
  if (typeof value === "string") return { [prefix]: value };
  return Object.entries(value as Record<string, unknown>).reduce(
    (all, [key, child]) => ({ ...all, ...flatten(child, prefix ? `${prefix}.${key}` : key) }),
    {} as Record<string, string>,
  );
}

function section(locale: string): Record<string, string> {
  const all = JSON.parse(fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8"));
  return flatten(all.creatorIde);
}

/** Simple `{name}` placeholders plus ICU plural arguments (`{count, plural, …}`). */
function placeholders(value: string): string[] {
  const names = new Set<string>();
  for (const match of value.matchAll(/\{(\w+)(?:,\s*plural)?[,}]/g)) names.add(match[1]);
  return [...names].sort();
}

const en = section("en");

describe("creatorIde messages", () => {
  it.each(locales.filter((locale) => locale !== "en"))("%s has every key and placeholder English has", (locale) => {
    const translated = section(locale);
    expect(Object.keys(translated).sort()).toEqual(Object.keys(en).sort());
    for (const [key, value] of Object.entries(en)) {
      expect({ key, placeholders: placeholders(translated[key]) }).toEqual({ key, placeholders: placeholders(value) });
    }
  });
});
