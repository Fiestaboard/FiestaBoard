import { beforeEach, describe, expect, it } from "vitest";

import {
  INSTALL_TRIGGER_KEY,
  isOfferDue,
  markNeverOffer,
  markOffered,
  readInstallTrigger,
  recordInstallSuccess,
  SNOOZE_MS,
} from "@/lib/pwa/install-trigger";

const DAY = 24 * 60 * 60 * 1000;

describe("install trigger (07 58:34443: after value, never on load)", () => {
  beforeEach(() => window.localStorage.clear());

  it("is not due after one or two sends", () => {
    expect(recordInstallSuccess("send", 0)).toBe(false);
    expect(recordInstallSuccess("send", 0)).toBe(false);
  });

  it("is due on the third send", () => {
    recordInstallSuccess("send", 0);
    recordInstallSuccess("send", 0);
    expect(recordInstallSuccess("send", 0)).toBe(true);
  });

  it("is due on the first saved page", () => {
    expect(recordInstallSuccess("save", 0)).toBe(true);
  });

  it("is held for 30 days once shown, and the next offer needs fresh value", () => {
    recordInstallSuccess("save", 0);
    markOffered(1000);
    expect(recordInstallSuccess("save", 1000 + SNOOZE_MS - 1)).toBe(false);
    // 30 days later, but the counts restarted at the offer: one save is fresh value.
    expect(recordInstallSuccess("save", 1000 + SNOOZE_MS)).toBe(true);
  });

  it("restarts the send count when the offer is shown", () => {
    for (let i = 0; i < 3; i++) recordInstallSuccess("send", 0);
    markOffered(0);
    expect(readInstallTrigger()).toMatchObject({ sends: 0, saves: 0, snoozedAt: 0 });
    expect(recordInstallSuccess("send", 31 * DAY)).toBe(false);
  });

  it("never comes back after Don't show again", () => {
    markNeverOffer();
    expect(recordInstallSuccess("save", 0)).toBe(false);
    expect(recordInstallSuccess("save", 365 * DAY)).toBe(false);
  });

  it("reads corrupt or missing storage as a fresh start", () => {
    window.localStorage.setItem(INSTALL_TRIGGER_KEY, "{not json");
    expect(readInstallTrigger()).toEqual({ sends: 0, saves: 0, snoozedAt: null, never: false });
    window.localStorage.setItem(INSTALL_TRIGGER_KEY, JSON.stringify({ sends: "x", never: "yes" }));
    expect(readInstallTrigger()).toEqual({ sends: 0, saves: 0, snoozedAt: null, never: false });
  });

  it("works without storage (private mode): never due from nothing, and never throws", () => {
    const broken = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    };
    expect(readInstallTrigger(broken)).toEqual({ sends: 0, saves: 0, snoozedAt: null, never: false });
    expect(() => markOffered(0, broken)).not.toThrow();
    expect(recordInstallSuccess("send", 0, null)).toBe(false);
  });

  it("isOfferDue honours the snooze boundary exactly", () => {
    const state = { sends: 3, saves: 0, snoozedAt: 0, never: false };
    expect(isOfferDue(state, SNOOZE_MS - 1)).toBe(false);
    expect(isOfferDue(state, SNOOZE_MS)).toBe(true);
  });
});
