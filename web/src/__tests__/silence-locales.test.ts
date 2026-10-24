import { describe, expect, it } from "vitest";

type Catalog = Record<string, Record<string, string>>;
const catalogs = import.meta.glob<Catalog>("../../messages/*.json", { eager: true, import: "default" });
const sections: Record<string, string[]> = {
  activeDisplay: [
    "silenceManual",
    "silenceSchedule",
    "silenceNoPage",
    "silenceHeld",
    "showNow",
    "discardHeld",
    "selectPageSilence",
    "toastSwitchHeld",
    "toastSwitchHeldNoTime",
    "toastSwitchPaused",
    "toastShownNow",
    "toastHeldDiscarded",
    "toastHeldDiscardFailed",
    "toastResendNotSent",
  ],
  forceSetDialog: ["silenceWarning", "confirmSilenced"],
  composeDialog: [
    "silenceHold",
    "silenceNoHold",
    "openSettings",
    "hold",
    "holdNoTime",
    "holding",
    "sendNowAnyway",
    "toastHeld",
    "toastHeldNoTime",
    "toastHoldError",
  ],
  pageBuilder: ["liveSilencePreviewOnly", "liveSendAnyway", "liveSilenceOverriding", "liveStopOverriding"],
  generalSettings: ["silenceShowHeldLabel", "silenceShowHeldHelp"],
  silenceNotice: ["untilTitle", "untilTitleNoTime"],
};
const english = catalogs["../../messages/en.json"];
const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();

describe("silence translations", () => {
  it("retains all 14 catalogs", () => expect(Object.keys(catalogs)).toHaveLength(14));
  it.each(Object.entries(catalogs))("%s has complete silence strings with matching placeholders", (_path, catalog) => {
    for (const [section, keys] of Object.entries(sections)) {
      for (const key of keys) {
        expect(catalog[section]?.[key], `${section}.${key}`).toBeTruthy();
        expect(placeholders(catalog[section][key])).toEqual(placeholders(english[section][key]));
      }
    }
  });
  it.each(Object.entries(catalogs))("%s directs Compose to the stable Behavior section", (_path, catalog) => {
    expect(catalog.composeDialog.silenceNoHold).toContain(catalog.settings.sectionBehavior);
  });
});
