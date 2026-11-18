import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

function mediaAt(initialWidth: number, coarse: boolean) {
  let width = initialWidth;
  const listeners = new Map<(event: MediaQueryListEvent) => void, string>();
  const matches = (query: string) => {
    if (query.includes("max-width: 1023px")) return width < 1024;
    if (query.includes("max-width: 767px")) return width < 768 || coarse;
    if (query.includes("max-width: 639px")) return width < 640;
    if (query.includes("min-width: 1280px")) return width >= 1280;
    if (query.includes("any-pointer: fine")) return !coarse;
    if (query.includes("pointer: coarse")) return coarse;
    return false;
  };
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return matches(query);
    },
    media: query,
    addEventListener: (_: string, callback: (event: MediaQueryListEvent) => void) => listeners.set(callback, query),
    removeEventListener: (_: string, callback: (event: MediaQueryListEvent) => void) => listeners.delete(callback),
  }));
  return (next: number) =>
    act(() => {
      width = next;
      listeners.forEach((query, listener) =>
        listener({ matches: matches(query), media: query } as MediaQueryListEvent),
      );
    });
}

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fiestaboard_editor_mode", "plain");
});
afterEach(() => vi.unstubAllGlobals());

describe("PageBuilder shortcut popup lifecycle", () => {
  it.each([
    [390, true],
    [900, false],
    [1024, true],
  ] as const)("opens hardware ? at %ipx/coarse=%s while More is closed", async (width, coarse) => {
    mediaAt(width, coarse);
    render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
    await screen.findByRole("textbox", { name: "Template" });
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    fireEvent.keyDown(document.body, { key: "?", shiftKey: true });
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
    expect(screen.getAllByRole("dialog", { name: "Keyboard shortcuts" })).toHaveLength(1);
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
  });

  it("opens the same stable popup from More and retains it and its focus through resize", async () => {
    const resize = mediaAt(900, false);
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
    const name = await screen.findByRole("textbox", { name: "Page Name" });
    await user.click(screen.getByRole("button", { name: "More" }));
    const more = await screen.findByRole("dialog", { name: "More" });
    await user.click(within(more).getByRole("button", { name: "Shortcuts" }));
    const popup = await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
    await waitFor(() => expect(popup).toHaveFocus());
    resize(1280);
    await waitFor(() => expect(screen.getAllByRole("dialog", { name: "Keyboard shortcuts" })).toHaveLength(1));
    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBe(popup);
    expect(popup).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Keyboard shortcuts" })).toBeNull());
    name.focus();
    resize(390);
    expect(name).toHaveFocus();
    expect(screen.queryByRole("dialog", { name: "Keyboard shortcuts" })).toBeNull();
  });
});
