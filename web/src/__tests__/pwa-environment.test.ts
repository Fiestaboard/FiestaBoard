import { describe, expect, it } from "vitest";

import { deviceWord, hubHost } from "@/lib/pwa/device-words";
import { canInstallOnSecureOrigin, isIosSafari, isSecureOrigin, isStandalone } from "@/lib/pwa/environment";

const UA = {
  iphoneSafari:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  iphoneChrome:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/131.0 Mobile/15E148 Safari/604.1",
  ipadosSafari:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
  macSafari:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
  desktopChrome:
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  androidChrome:
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
  firefox: "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
  edge: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0",
};

function win(userAgent: string, opts: { touch?: number; standalone?: boolean; displayMode?: boolean } = {}) {
  return {
    isSecureContext: true,
    matchMedia: (q: string) => ({ matches: q.includes("standalone") && opts.displayMode === true }) as MediaQueryList,
    navigator: { userAgent, maxTouchPoints: opts.touch ?? 0, standalone: opts.standalone },
  };
}

describe("isSecureOrigin", () => {
  it("is true only when the browser says the context is secure", () => {
    expect(isSecureOrigin({ isSecureContext: true })).toBe(true);
    expect(isSecureOrigin({ isSecureContext: false })).toBe(false);
  });
});

describe("isStandalone", () => {
  it("is true in an installed app's window", () => {
    expect(isStandalone(win(UA.desktopChrome, { displayMode: true }))).toBe(true);
  });
  it("is true for an iOS Home Screen web app", () => {
    expect(isStandalone(win(UA.iphoneSafari, { standalone: true }))).toBe(true);
  });
  it("is false in a browser tab", () => {
    expect(isStandalone(win(UA.desktopChrome))).toBe(false);
  });
  it("is false when matchMedia throws", () => {
    const w = {
      ...win(UA.desktopChrome),
      matchMedia: () => {
        throw new Error("no");
      },
    };
    expect(isStandalone(w as never)).toBe(false);
  });
});

describe("isIosSafari", () => {
  it.each([
    ["iPhone Safari", UA.iphoneSafari, 5, true],
    ["iPadOS Safari (Mac UA with touch)", UA.ipadosSafari, 5, true],
    ["Chrome on iPhone", UA.iphoneChrome, 5, false],
    ["Safari on a Mac", UA.macSafari, 0, false],
    ["desktop Chrome", UA.desktopChrome, 0, false],
  ])("%s → %s", (_name, ua, touch, expected) => {
    expect(isIosSafari(win(ua, { touch }))).toBe(expected);
  });
});

describe("canInstallOnSecureOrigin", () => {
  it.each([
    ["desktop Chrome", UA.desktopChrome, 0, true],
    ["Android Chrome", UA.androidChrome, 5, true],
    ["Edge", UA.edge, 0, true],
    ["iPhone Safari", UA.iphoneSafari, 5, true],
    ["Chrome on iPhone (no Safari steps)", UA.iphoneChrome, 5, false],
    ["Firefox", UA.firefox, 0, false],
    ["Safari on a Mac", UA.macSafari, 0, false],
  ])("%s → %s", (_name, ua, touch, expected) => {
    expect(canInstallOnSecureOrigin(win(ua, { touch }))).toBe(expected);
  });
});

describe("device words", () => {
  it("calls a phone or tablet a phone, anything else a computer", () => {
    expect(deviceWord(UA.iphoneSafari)).toBe("phone");
    expect(deviceWord(UA.androidChrome)).toBe("phone");
    expect(deviceWord(UA.desktopChrome)).toBe("computer");
  });
  it("names the hub by the address the page was opened at", () => {
    expect(hubHost({ host: "fiestapi.local:4420" })).toBe("fiestapi.local:4420");
  });
});
