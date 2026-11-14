/**
 * A display the hub can't reach (H12): its board preview shows the destructive
 * "Offline" badge with when it was last connected, and the last-known board is
 * dimmed so it never reads as live (07a `310:38645`).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { LastKnownBoard } from "@/components/status-banners/last-known-board";

import { server } from "./mocks/server";

const HEALTHY = {
  last_connected_at: "2026-11-13T22:00:00+00:00",
  last_update_at: null,
  latency_ms: 40,
  last_error_at: null,
  last_error: null,
  reachable: true,
  breaker_open: false,
};

function withHealth(health: Record<string, unknown>) {
  server.use(
    http.get("/api/v1/status", () =>
      HttpResponse.json({
        running: true,
        initialized: true,
        config_summary: {},
        boards: { clock: { configured: true, paused: false, active_page_id: null, health } },
      }),
    ),
  );
}

function renderBoard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LastKnownBoard boardId="clock">
        <div data-testid="board">board</div>
      </LastKnownBoard>
    </QueryClientProvider>,
  );
}

describe("LastKnownBoard", () => {
  it("badges an offline display and dims its last-known board", async () => {
    withHealth({ ...HEALTHY, reachable: false, last_error: "unreachable", last_error_at: "2026-11-13T22:05:00Z" });
    renderBoard();
    expect(await screen.findByText("Offline")).toBeInTheDocument();
    expect(screen.getByText(/^Last connected .+ · Schedule keeps running on the hub$/)).toBeInTheDocument();
    const preview = screen.getByTestId("board").closest('[data-slot="last-known-board-preview"]');
    expect(preview).toHaveClass("opacity-60");
  });

  it("says it was never reached when there is no last connection", async () => {
    withHealth({ ...HEALTHY, reachable: false, last_connected_at: null });
    renderBoard();
    expect(await screen.findByText(/^Not reached since the hub started/)).toBeInTheDocument();
  });

  it("leaves a reachable display, or one whose health is unknown, untouched", async () => {
    withHealth({ ...HEALTHY, reachable: null });
    const { container } = renderBoard();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId("board")).toBeInTheDocument();
    expect(container.querySelector('[data-slot="last-known-board"]')).toBeNull();
    expect(screen.queryByText("Offline")).not.toBeInTheDocument();
  });
});
