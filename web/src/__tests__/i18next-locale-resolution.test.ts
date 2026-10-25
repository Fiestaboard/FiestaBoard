/**
 * The detected locale must resolve to one of our bare language codes.
 * A browser reporting "en-US" (jsdom's navigator.language) has to land on
 * "en": RootBody writes `i18n.language` into `<html lang>`, and the lazy
 * locale backend only knows bare codes.
 */
import { describe, expect, it } from "vitest";

import i18n, { i18nReady } from "@/i18n/i18next";

describe("i18next locale resolution", () => {
  it("resolves a regional browser locale to its bare language code", async () => {
    await i18nReady;

    expect(navigator.language).toBe("en-US");
    expect(i18n.language).toBe("en");
  });
});
