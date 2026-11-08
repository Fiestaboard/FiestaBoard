import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InstallPrompt } from "@/components/install-prompt";

function showBanner() {
  const beforeInstall = new Event("beforeinstallprompt") as Event & {
    prompt?: () => Promise<void>;
    userChoice?: Promise<{ outcome: "accepted" | "dismissed" }>;
  };
  beforeInstall.prompt = vi.fn().mockResolvedValue(undefined);
  beforeInstall.userChoice = Promise.resolve({ outcome: "dismissed" as const });

  act(() => {
    window.dispatchEvent(beforeInstall);
  });
  act(() => {
    vi.advanceTimersByTime(2000);
  });
  return beforeInstall;
}

describe("InstallPrompt", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("announces the install banner with a polite aria-live region", async () => {
    render(<InstallPrompt />);

    const beforeInstall = new Event("beforeinstallprompt") as Event & {
      prompt?: () => Promise<void>;
      userChoice?: Promise<{ outcome: "accepted" | "dismissed" }>;
    };
    beforeInstall.prompt = vi.fn().mockResolvedValue(undefined);
    beforeInstall.userChoice = Promise.resolve({ outcome: "dismissed" as const });

    act(() => {
      window.dispatchEvent(beforeInstall);
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    const banner = screen.getByRole("status");
    expect(banner).toHaveAttribute("aria-live", "polite");
    expect(banner).toHaveTextContent(/install/i);
  });

  it.each(["/p/3", "/panel/abc123"])("never shows on the chromeless panel viewer (%s)", (path) => {
    const before = window.location.pathname;
    window.history.pushState({}, "", path);
    try {
      render(<InstallPrompt />);
      const beforeInstall = Object.assign(new Event("beforeinstallprompt"), {
        prompt: vi.fn().mockResolvedValue(undefined),
        userChoice: Promise.resolve({ outcome: "dismissed" as const }),
      });
      act(() => {
        window.dispatchEvent(beforeInstall);
      });
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    } finally {
      window.history.pushState({}, "", before);
    }
  });
  it("hides the banner and remembers the choice when Not now is pressed", () => {
    render(<InstallPrompt />);
    showBanner();

    fireEvent.click(screen.getByRole("button", { name: /not now/i }));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("pwa-install-dismissed")).not.toBeNull();
  });

  it("opens the browser install prompt when Install is pressed", () => {
    render(<InstallPrompt />);
    const beforeInstall = showBanner();

    fireEvent.click(screen.getByRole("button", { name: /^install/i }));

    expect(beforeInstall.prompt).toHaveBeenCalled();
  });
});
