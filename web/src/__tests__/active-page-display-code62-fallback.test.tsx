import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
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

/**
 * Deliberately rendered WITHOUT CurrentBoardProvider, so `useCurrentBoard()`
 * yields the default `currentBoard: undefined` — the pre-load window the
 * board_color fallback beside it already covers (issue #1657).
 */
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

function useHeartBoard() {
  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({
        board_type: "black",
        boards: [
          {
            id: "default",
            name: "Flagship",
            device_type: "flagship",
            board_color: "black",
            code62_glyph: "heart",
            enabled: true,
          },
        ],
        devices: ["flagship"],
      }),
    ),
    http.get(`${API_BASE}/board/current-message`, () =>
      HttpResponse.json({
        characters: [],
        message: "72°F",
        rows: 6,
        cols: 22,
        expected_characters: null,
        cached_at: null,
        api_mode: "local",
      }),
    ),
  );
}

describe("ActivePageDisplay code-62 flap fallback", () => {
  it("draws the stored heart flap before the current board has resolved", async () => {
    useHeartBoard();

    render(
      <TestWrapper>
        <ActivePageDisplay />
      </TestWrapper>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("char-tile-0-2")).toHaveTextContent("♥");
    });
  });
});
