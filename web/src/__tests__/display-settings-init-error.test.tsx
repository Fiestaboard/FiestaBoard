/**
 * Per-board init errors in DisplaySettings (issue #1829).
 *
 * The backend records why a board failed to initialize (issue #1749) and
 * exposes it as `GET /status` → `boards[<id>].error`. The board card in
 * hardware settings must surface it: an "Unavailable" badge on the collapsed
 * header, and the verbatim reason string inside the expanded card.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DisplaySettings } from "@/components/settings/display-settings";

import { server } from "./mocks/server";

const API_BASE = "/api";

const INIT_ERROR = "Local API key rejected by board at 192.0.2.55";

function setupHandlers({ error }: { error?: string | null } = {}) {
  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({
        board_type: "black",
        boards: [
          {
            id: "default",
            name: "My Board",
            device_type: "flagship",
            board_color: "black",
            api_mode: "cloud",
            cloud_key: "***",
          },
        ],
        devices: ["flagship"],
      }),
    ),
    http.get(`${API_BASE}/status`, () =>
      HttpResponse.json({
        running: true,
        initialized: true,
        config_summary: {},
        boards: {
          default: {
            configured: !error,
            paused: false,
            active_page_id: null,
            ...(error !== undefined ? { error } : {}),
          },
        },
      }),
    ),
  );
}

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("DisplaySettings — board init error surfacing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows an Unavailable badge on the board card when status reports an init error", async () => {
    setupHandlers({ error: INIT_ERROR });
    render(<DisplaySettings />, { wrapper: TestWrapper });

    const badge = await screen.findByTestId("board-init-error-badge");
    expect(badge).toHaveTextContent("Unavailable");
  });

  it("shows the verbatim reason string inside the expanded card", async () => {
    const user = userEvent.setup();
    setupHandlers({ error: INIT_ERROR });
    render(<DisplaySettings />, { wrapper: TestWrapper });

    await user.click(await screen.findByText("My Board"));

    const detail = await screen.findByTestId("board-init-error-detail");
    expect(detail).toHaveTextContent("This board failed to initialize");
    expect(detail).toHaveTextContent(INIT_ERROR);
  });

  it("renders no badge and no detail when the board has no init error", async () => {
    const user = userEvent.setup();
    setupHandlers({ error: null });
    render(<DisplaySettings />, { wrapper: TestWrapper });

    await user.click(await screen.findByText("My Board"));
    await screen.findByTestId("board-card");

    expect(screen.queryByTestId("board-init-error-badge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("board-init-error-detail")).not.toBeInTheDocument();
  });
});
