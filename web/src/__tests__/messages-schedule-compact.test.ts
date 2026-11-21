/**
 * The compact schedule entry form's strings (BB-C-5, kit 8.17.0-alpha.4) live
 * in `schedule.adapter`, in every locale, and are translated.
 */
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

import { locales } from "@/i18n/config";

const messagesDir = path.resolve(__dirname, "../../messages");
const adapter = (locale: string) =>
  JSON.parse(fs.readFileSync(path.join(messagesDir, `${locale}.json`), "utf-8")).schedule.adapter;
const strings = (a: Record<string, unknown>) => [
  a.moreOptions,
  a.timeRangeTo,
  (a.startsAtSun as Record<string, string> | undefined)?.sunrise,
  (a.startsAtSun as Record<string, string> | undefined)?.sunset,
  (a.endsAtSun as Record<string, string> | undefined)?.sunrise,
  (a.endsAtSun as Record<string, string> | undefined)?.sunset,
  a.entryOff,
];

describe("schedule.adapter compact labels", () => {
  it.each(locales)("%s has every compact label as a non-empty string", (locale) => {
    for (const value of strings(adapter(locale))) expect(typeof value === "string" && value.trim()).toBeTruthy();
  });
  it.each(locales.filter((l) => l !== "en"))("%s translates the sentence labels", (locale) => {
    const en = strings(adapter("en"));
    const local = strings(adapter(locale));
    for (const i of [0, 2, 3, 4, 5, 6]) expect(local[i]).not.toBe(en[i]);
  });
});
