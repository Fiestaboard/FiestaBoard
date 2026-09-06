/**
 * Dashboard banner for boards that failed to initialize (issue #1829).
 *
 * `GET /status` → `boards[<id>].error` (issue #1749) names the boards the
 * backend skipped at startup. The home dashboard renders one alert per
 * failed board — with the board's name, the verbatim reason, and a jump to
 * hardware settings — and renders nothing at all for a healthy fleet.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BoardInitErrorBanner } from "@/components/board-init-error-banner";
import { CurrentBoardProvider } from "@/components/current-board-context";

import { server } from "./mocks/server";

const API_BASE = "/api";

const INIT_ERROR = "Cloud API key rejected (HTTP 401)";

const mockPush = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
}));

function setupHandlers({ boardsStatus }: { boardsStatus?: Record<string, unknown> } = {}) {
  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({
        board_type: "black",
        boards: [
          { id: "board-1", name: "Kitchen", device_type: "flagship", board_color: "black" },
          { id: "board-2", name: "Office", device_type: "note", board_color: "white" },
        ],
        devices: ["flagship", "note"],
      }),
    ),
    http.get(`${API_BASE}/status`, () =>
      HttpResponse.json({
        running: true,
        initialized: true,
        config_summary: {},
        ...(boardsStatus !== undefined ? { boards: boardsStatus } : {}),
      }),
    ),
  );
}

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <CurrentBoardProvider>{children}</CurrentBoardProvider>
    </QueryClientProvider>
  );
}

describe("BoardInitErrorBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders an alert naming the failed board with the translated message and verbatim reason", async () => {
    setupHandlers({
      boardsStatus: {
        "board-1": { configured: true, paused: false, active_page_id: null },
        "board-2": { configured: false, paused: false, active_page_id: null, error: INIT_ERROR },
      },
    });
    render(<BoardInitErrorBanner />, { wrapper: TestWrapper });

    const banner = await screen.findByTestId("board-init-error-banner");
    expect(banner).toHaveTextContent("Office is unavailable");
    expect(banner).toHaveTextContent(INIT_ERROR);
  });

  it("renders nothing when no board reports an init error", async () => {
    setupHandlers({
      boardsStatus: {
        "board-1": { configured: true, paused: false, active_page_id: null, error: null },
        "board-2": { configured: true, paused: false, active_page_id: null },
      },
    });
    const { container } = render(<BoardInitErrorBanner />, { wrapper: TestWrapper });

    // Let the status query resolve, then assert the banner never appeared.
    await expect(
      waitFor(() => expect(screen.getByTestId("board-init-error-banner")).toBeInTheDocument(), { timeout: 300 }),
    ).rejects.toThrow();
    expect(container).toBeEmptyDOMElement();
  });

  it("navigates to hardware settings from the alert's action", async () => {
    const user = userEvent.setup();
    setupHandlers({
      boardsStatus: {
        "board-1": { configured: false, paused: false, active_page_id: null, error: INIT_ERROR },
      },
    });
    render(<BoardInitErrorBanner />, { wrapper: TestWrapper });

    await screen.findByTestId("board-init-error-banner");
    await user.click(screen.getByRole("button", { name: "Open board settings" }));

    expect(mockPush).toHaveBeenCalledWith("/settings?section=hardware");
  });
});
