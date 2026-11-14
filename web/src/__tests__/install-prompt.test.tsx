import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INSTALL_OFFER_SLOT_ID, InstallPrompt } from "@/components/install-prompt";
import { emitApiSuccess } from "@/lib/api/success-events";
import { INSTALL_TRIGGER_KEY, readInstallTrigger } from "@/lib/pwa/install-trigger";

const CHROME =
  "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36";
const IPHONE_SAFARI =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0";

function setBrowser({ ua = CHROME, secure = true, standalone = false } = {}) {
  vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue(ua);
  Object.defineProperty(window, "isSecureContext", { configurable: true, value: secure });
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: standalone && q.includes("standalone"),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

function stashInstallEvent(outcome: "accepted" | "dismissed" = "dismissed") {
  const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome }),
  });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

const send = () => act(() => emitApiSuccess("POST", "/v1/boards/b1/message"));
const savePage = () => act(() => emitApiSuccess("POST", "/v1/pages"));
const card = () => screen.queryByTestId("install-offer");

describe("InstallPrompt (WEB-12)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setBrowser();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows nothing on load, even when the browser offers to install", () => {
    render(<InstallPrompt />);
    const event = stashInstallEvent();
    expect(event.defaultPrevented).toBe(true);
    expect(card()).not.toBeInTheDocument();
  });

  it("shows nothing after one or two sends", () => {
    render(<InstallPrompt />);
    stashInstallEvent();
    send();
    send();
    expect(card()).not.toBeInTheDocument();
  });

  it("offers a real Install button after the third send", () => {
    render(<InstallPrompt />);
    stashInstallEvent();
    send();
    send();
    send();
    const offer = within(card()!);
    expect(offer.getByRole("region", { name: /add fiestaboard control to this phone/i })).toBeInTheDocument();
    expect(offer.getByText(/you’ve sent 3 messages from here/i)).toBeInTheDocument();
    expect(offer.getByRole("button", { name: /^install$/i })).toBeInTheDocument();
  });

  it("offers after the first saved page", () => {
    render(<InstallPrompt />);
    stashInstallEvent();
    savePage();
    expect(within(card()!).getByText(/you saved a page from here/i)).toBeInTheDocument();
  });

  it("ignores successes that are not sends or saves", () => {
    render(<InstallPrompt />);
    stashInstallEvent();
    for (let i = 0; i < 5; i++) act(() => emitApiSuccess("GET", "/v1/pages"));
    expect(card()).not.toBeInTheDocument();
  });

  it("opens the browser's own prompt from Install, then goes away for good when accepted", async () => {
    render(<InstallPrompt />);
    const event = stashInstallEvent("accepted");
    savePage();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^install$/i }));
    });
    expect(event.prompt).toHaveBeenCalledTimes(1);
    expect(card()).not.toBeInTheDocument();
    expect(readInstallTrigger().never).toBe(true);
  });

  it("Not now hides the card and snoozes it for 30 days", () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
    render(<InstallPrompt />);
    stashInstallEvent();
    savePage();
    fireEvent.click(screen.getByRole("button", { name: /not now/i }));
    expect(card()).not.toBeInTheDocument();
    expect(readInstallTrigger().snoozedAt).toBe(1_000_000);
    savePage();
    expect(card()).not.toBeInTheDocument();
    now.mockRestore();
  });

  it("on plain http says Install needs a secure address and draws no Install button", () => {
    setBrowser({ secure: false });
    render(<InstallPrompt />);
    savePage();
    const offer = within(card()!);
    expect(offer.getByRole("region", { name: /install needs a secure address/i })).toBeInTheDocument();
    expect(offer.queryByRole("button", { name: /^install$/i })).not.toBeInTheDocument();
    expect(offer.getByRole("button", { name: /not now/i })).toBeInTheDocument();
    expect(offer.getByRole("link", { name: /how to set up https/i })).toHaveAttribute(
      "href",
      expect.stringContaining("fiestaboard.app/docs/deployment/production"),
    );
  });

  it("opens Safari's Add to Home Screen steps on an iPhone, at the same moment", () => {
    setBrowser({ ua: IPHONE_SAFARI });
    render(<InstallPrompt />);
    savePage();
    const sheet = screen.getByRole("dialog", { name: /add to your home screen/i });
    const steps = within(sheet).getAllByRole("listitem");
    expect(steps.map((s) => s.textContent)).toEqual([
      expect.stringContaining("Tap ⋯ in Safari’s address bar"),
      expect.stringContaining("Add to Home Screen"),
      expect.stringContaining("Open as Web App"),
    ]);
  });

  it("Don't show again on the Safari sheet ends the offer for good", () => {
    setBrowser({ ua: IPHONE_SAFARI });
    render(<InstallPrompt />);
    savePage();
    fireEvent.click(screen.getByRole("button", { name: /don’t show again/i }));
    expect(readInstallTrigger().never).toBe(true);
  });

  it("Got it on the Safari sheet just closes it (snoozed, not ended)", () => {
    setBrowser({ ua: IPHONE_SAFARI });
    render(<InstallPrompt />);
    savePage();
    fireEvent.click(screen.getByRole("button", { name: /got it/i }));
    expect(readInstallTrigger().never).toBe(false);
    expect(readInstallTrigger().snoozedAt).not.toBeNull();
  });

  it("keeps the count but shows nothing when a secure Chromium browser has offered nothing to install", () => {
    render(<InstallPrompt />);
    savePage();
    expect(card()).not.toBeInTheDocument();
    expect(readInstallTrigger().snoozedAt).toBeNull();
  });

  it("shows nothing in an already installed app", () => {
    setBrowser({ standalone: true });
    render(<InstallPrompt />);
    stashInstallEvent();
    savePage();
    expect(card()).not.toBeInTheDocument();
    expect(window.localStorage.getItem(INSTALL_TRIGGER_KEY)).toBeNull();
  });

  it("shows nothing in a browser that can't install apps at all (no false https promise)", () => {
    setBrowser({ ua: FIREFOX, secure: false });
    render(<InstallPrompt />);
    savePage();
    expect(card()).not.toBeInTheDocument();
  });

  it("ends the offer when the browser reports the app installed", () => {
    render(<InstallPrompt />);
    stashInstallEvent();
    savePage();
    act(() => {
      window.dispatchEvent(new Event("appinstalled"));
    });
    expect(card()).not.toBeInTheDocument();
    expect(readInstallTrigger().never).toBe(true);
  });

  it.each(["/p/3", "/panel/abc123"])("never shows on the chromeless panel viewer (%s)", (path) => {
    const before = window.location.pathname;
    window.history.pushState({}, "", path);
    try {
      render(<InstallPrompt />);
      stashInstallEvent();
      savePage();
      expect(card()).not.toBeInTheDocument();
    } finally {
      window.history.pushState({}, "", before);
    }
  });

  it("renders inside a page's install slot when the page provides one", () => {
    const slot = document.createElement("div");
    slot.id = INSTALL_OFFER_SLOT_ID;
    document.body.appendChild(slot);
    try {
      render(<InstallPrompt />);
      stashInstallEvent();
      savePage();
      expect(slot).toContainElement(card());
    } finally {
      slot.remove();
    }
  });
});
