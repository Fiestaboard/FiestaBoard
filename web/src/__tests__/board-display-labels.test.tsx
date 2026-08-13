/**
 * The board's accessible name comes from the app's translations.
 *
 * `@fiestaboard/ui`'s `BoardDisplay` is presentational: it takes
 * `loadingLabel` / `emptyLabel` / `messageLabel` as props and falls back to
 * hardcoded English when they are not passed. Those fallbacks are *identical*
 * to this app's `en.json` strings, so an English assertion would pass whether
 * or not the wrapper wires anything up — it would be a vacuous test.
 *
 * So this file replaces the global English i18n mock with a sentinel `t` whose
 * output no fallback can imitate. If the wrapper stops passing a label prop,
 * the package's English default appears instead and the assertion fails.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import { BoardDisplay } from "@/components/board-display";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { StaticBoardDisplay } from "@/components/static-board-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

/**
 * A stand-in locale. `t("empty")` becomes `[[boardDisplay.empty]]`, and
 * `t("withMessage", { message })` becomes `[[boardDisplay.withMessage|<text>]]`
 * — a shape the package cannot produce on its own.
 */
const T_CACHE = new Map<string, unknown>();
vi.mock("@/i18n/translations", () => ({
  useTranslations: (namespace?: string) => {
    const ns = namespace ?? "";
    const cached = T_CACHE.get(ns);
    // Stable across renders, like the real hook — an unstable `t` defeats the
    // memoization this wrapper deliberately preserves (see #1570).
    if (cached !== undefined) return cached;
    const t = (key: string, params?: Record<string, unknown>) =>
      params ? `[[${ns}.${key}|${Object.values(params).join(",")}]]` : `[[${ns}.${key}]]`;
    T_CACHE.set(ns, t);
    return t;
  },
  useLocale: () => "xx",
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

describe("board accessible names are translated by the app", () => {
  it("names a board showing a message with the app's withMessage translation", () => {
    render(<BoardDisplay message="HELLO" size="sm" />, { wrapper: TestWrapper });

    const label = screen.getByRole("img").getAttribute("aria-label");
    expect(label).toContain("boardDisplay.withMessage");
    expect(label).toContain("HELLO");
  });

  it("names an empty board with the app's empty translation", () => {
    render(<BoardDisplay message={null} size="sm" />, { wrapper: TestWrapper });

    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "[[boardDisplay.empty]]");
  });

  it("names a loading board with the app's loading translation", () => {
    render(<BoardDisplay message="HELLO" isLoading size="sm" />, { wrapper: TestWrapper });

    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "[[boardDisplay.loading]]");
  });

  it("names a scaled board with the app's translations too", () => {
    render(<ScaledBoardDisplay message="HELLO" size="sm" />, { wrapper: TestWrapper });

    const label = screen.getByRole("img").getAttribute("aria-label");
    expect(label).toContain("boardDisplay.withMessage");
  });

  it("names a static preview with the app's preview translation", () => {
    render(<StaticBoardDisplay message="HELLO" size="sm" />, { wrapper: TestWrapper });

    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "[[boardDisplay.preview]]");
  });
});
