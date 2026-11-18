import { toast } from "@fiestaboard/ui/components/feedback/toaster";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n, { i18nReady } from "@/i18n/i18next";

// Exercise the app's real locale subscription and the kit's real Sonner host.
vi.unmock("@/i18n/translations");

function setSystemTheme(dark: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query) =>
      ({
        matches: query === "(prefers-color-scheme: dark)" && dark,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

async function showToast() {
  act(() => {
    toast.success("Saved to Pages", { duration: Infinity });
  });
  await screen.findByText("Saved to Pages");
  const element = document.querySelector<HTMLElement>("[data-sonner-toaster]");
  expect(element).not.toBeNull();
  return element!;
}

describe("app toast host uses the shared kit surface", () => {
  beforeEach(async () => {
    await i18nReady;
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    localStorage.removeItem("theme");
    setSystemTheme(false);
  });

  afterEach(async () => {
    act(() => toast.dismiss());
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    localStorage.removeItem("theme");
    document.documentElement.classList.remove("dark");
    vi.restoreAllMocks();
  });

  it("uses snackbar sizing and keeps its mobile side insets while clearing navigation", async () => {
    render(<Toaster />);
    const element = await showToast();
    expect(element.style.getPropertyValue("--width")).toBe("380px");
    expect(element.style.getPropertyValue("--mobile-offset-left")).toBe("8px");
    expect(element.style.getPropertyValue("--mobile-offset-right")).toBe("8px");
    expect(element.style.getPropertyValue("--offset-bottom")).toBe(
      "calc(24px + var(--bottom-nav-offset, 0px) + env(safe-area-inset-bottom, 0px))",
    );
  });

  it("updates the live-region and close names when the active locale changes", async () => {
    render(<Toaster closeButton />);
    await showToast();
    expect(screen.getByRole("region", { name: /^Notifications/ })).toHaveAttribute("aria-live", "polite");
    await act(async () => {
      await i18n.changeLanguage("es");
    });
    expect(screen.getByRole("region", { name: /^Notificaciones/ })).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("button", { name: "Cerrar" })).toBeInTheDocument();
  });

  it("preserves explicit kit label overrides", async () => {
    render(<Toaster closeButton labels={{ container: "Editor notices", close: "Dismiss notice" }} />);
    await showToast();
    expect(screen.getByRole("region", { name: /^Editor notices/ })).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("button", { name: "Dismiss notice" })).toBeInTheDocument();
  });

  it("retains the legacy container-name override alongside the kit close label", async () => {
    render(
      <Toaster
        closeButton
        containerAriaLabel="Display notices"
        labels={{ container: "Editor notices", close: "Dismiss notice" }}
      />,
    );
    await showToast();
    expect(screen.getByRole("region", { name: /^Display notices/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss notice" })).toBeInTheDocument();
  });

  it.each([false, true])("uses the resolved system theme when dark preference is %s", async (dark) => {
    setSystemTheme(dark);
    render(
      <ThemeProvider defaultTheme="system">
        <Toaster />
      </ThemeProvider>,
    );
    const element = await showToast();
    expect(element).toHaveAttribute("data-sonner-theme", dark ? "dark" : "light");
  });

  it("keeps an explicit host theme ahead of the app theme", async () => {
    setSystemTheme(true);
    render(
      <ThemeProvider defaultTheme="dark">
        <Toaster theme="light" />
      </ThemeProvider>,
    );
    const element = await showToast();
    expect(document.documentElement).toHaveClass("dark");
    await waitFor(() => expect(element).toHaveAttribute("data-sonner-theme", "light"));
  });
});
