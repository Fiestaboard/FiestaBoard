import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InstallPrompt } from "@/components/install-prompt";

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
});
