import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { HOME_COLOR_STRIP_KEY } from "@/hooks/use-home-color-strip";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
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

afterEach(() => localStorage.removeItem(HOME_COLOR_STRIP_KEY));

function useBoard() {
  server.use(
    http.get(`${API_BASE}/board/current-message`, () =>
      HttpResponse.json({
        characters: [],
        message: "HELLO",
        rows: 6,
        cols: 22,
        expected_characters: null,
        cached_at: null,
        api_mode: "local",
      }),
    ),
  );
}

// BB-FC-12: 07e Appearance › Boards "Show the color strip on Home".
describe("Home Now showing colour strip", () => {
  it("draws the colour strip under the Now showing board", async () => {
    useBoard();
    render(
      <TestWrapper>
        <ActivePageDisplay />
      </TestWrapper>,
    );
    const strip = await screen.findByTestId("home-color-strip");
    await waitFor(() => expect(screen.getByTestId("char-tile-0-0")).toBeInTheDocument());
    // Below the board, never inside it: the board shows only what is on the wall.
    const board = screen.getByTestId("home-board-state");
    expect(board.contains(strip)).toBe(false);
    expect(board.compareDocumentPosition(strip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("leaves it out when this browser turned it off", async () => {
    localStorage.setItem(HOME_COLOR_STRIP_KEY, "off");
    useBoard();
    render(
      <TestWrapper>
        <ActivePageDisplay />
      </TestWrapper>,
    );
    await waitFor(() => expect(screen.getByTestId("char-tile-0-0")).toBeInTheDocument());
    expect(screen.queryByTestId("home-color-strip")).not.toBeInTheDocument();
  });
});
