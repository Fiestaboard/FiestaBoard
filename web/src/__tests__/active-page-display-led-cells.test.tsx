/**
 * The home live preview of a board whose output took rich cells (an LED
 * output) draws those cells — colour, case and icons — rather than the 0–71
 * `message`, which cannot hold them. A split-flap board is untouched.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { CurrentBoardProvider } from "@/components/current-board-context";
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

const PIXOO_BOARD = {
  board_type: "black",
  boards: [
    {
      id: "px1",
      name: "Desk",
      device_type: "panel",
      device_model: "divoom_pixoo64",
      output: "divoom_pixoo",
      grid_rows: 8,
      grid_cols: 10,
      board_color: "black",
      enabled: true,
    },
  ],
  devices: ["panel"],
};

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

function currentMessage(extra: Record<string, unknown>) {
  server.use(
    http.get(`${API_BASE}/settings/board`, () => HttpResponse.json(PIXOO_BOARD)),
    http.get(`${API_BASE}/board/current-message`, () =>
      HttpResponse.json({
        characters: [[1]],
        message: "FLAPS",
        rows: 8,
        cols: 10,
        expected_characters: null,
        cached_at: null,
        api_mode: "local",
        board_id: null,
        ...extra,
      }),
    ),
  );
}

describe("the home live preview of a rich board", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("draws the frame's rich cells when the API sends them", async () => {
    currentMessage({ cells: [[..."Cells"].map((value) => ({ type: "char", value, color: "red" }))] });
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Cells"), {
      timeout: 3000,
    });
    expect(screen.getByRole("img").getAttribute("aria-label")).not.toContain("FLAPS");
  });

  it("draws the message when the frame has no cells", async () => {
    currentMessage({});
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByRole("img").getAttribute("aria-label")).toContain("FLAPS"), {
      timeout: 3000,
    });
  });
});
