import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { isInDimWindow } from "@/components/panel/panel-view";
import { PanelView } from "@/components/panel/panel-view";
import type { PanelFrame, PanelPublicConfig } from "@/lib/api";

import { server } from "./mocks/server";

const CONFIG: PanelPublicConfig = {
  id: "p1",
  name: "Living Room TV",
  board_id: "vboard-1",
  screen_diagonal_inches: 55,
  calibration_scale: 1,
  backdrop: "wall",
  auto_dim: { enabled: false, start: "22:00", end: "07:00" },
  created_at: "2026-08-25T00:00:00+00:00",
  updated_at: "2026-08-25T00:00:00+00:00",
  device_type: "note_array",
  board_missing: false,
  rows: 6,
  cols: 30,
  board_color: "black",
  code62_glyph: "heart",
};

const FRAME: PanelFrame = {
  characters: null,
  message: "HELLO PANEL",
  rows: 6,
  cols: 30,
  updated_at: "2026-08-25T00:00:00+00:00",
};

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function mockPanel(config: PanelPublicConfig = CONFIG, frame: PanelFrame = FRAME) {
  server.use(
    http.get("/api/panel/p1", () => HttpResponse.json(config)),
    http.get("/api/panel/p1/frame", () => HttpResponse.json(frame)),
  );
}

describe("PanelView", () => {
  it("renders the frame's message on the board", async () => {
    mockPanel();
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    const board = await screen.findByRole("img");
    expect(board.getAttribute("aria-label")).toContain("HELLO PANEL");
  });

  it("shows the not-found state for a deleted panel", async () => {
    server.use(
      http.get("/api/panel/p1", () => HttpResponse.json({ detail: "Panel not found" }, { status: 404 })),
      http.get("/api/panel/p1/frame", () => HttpResponse.json({ detail: "Panel not found" }, { status: 404 })),
    );
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    expect(await screen.findByText("This panel no longer exists")).toBeInTheDocument();
  });

  it("keeps the last frame and shows an offline dot when polling fails", async () => {
    mockPanel();
    render(<PanelView panelId="p1" frameIntervalMs={40} configIntervalMs={100000} />, {
      wrapper: Wrapper,
    });
    await screen.findByRole("img");
    server.use(http.get("/api/panel/p1/frame", () => HttpResponse.error()));
    await waitFor(() => expect(screen.getByTestId("panel-offline")).toBeInTheDocument(), {
      timeout: 5000,
    });
    // the last good frame is still on the glass
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("HELLO PANEL");
  });

  it("shows the auto-dim overlay when inside the window", async () => {
    mockPanel({
      ...CONFIG,
      auto_dim: { enabled: true, start: "00:00", end: "23:59" },
    });
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    await waitFor(() => {
      expect(screen.getByTestId("panel-dim")).toHaveAttribute("data-active", "true");
    });
  });

  it("reports the orphaned-board state", async () => {
    mockPanel({ ...CONFIG, board_missing: true, device_type: null, rows: null, cols: null });
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    expect(await screen.findByText("This panel's board was removed")).toBeInTheDocument();
  });
});

describe("isInDimWindow", () => {
  const minutes = (h: number, m: number) => h * 60 + m;

  it("handles a same-day window", () => {
    expect(isInDimWindow(minutes(12, 0), "09:00", "17:00")).toBe(true);
    expect(isInDimWindow(minutes(8, 59), "09:00", "17:00")).toBe(false);
    expect(isInDimWindow(minutes(17, 0), "09:00", "17:00")).toBe(false);
  });

  it("handles an overnight window", () => {
    expect(isInDimWindow(minutes(23, 30), "22:00", "07:00")).toBe(true);
    expect(isInDimWindow(minutes(3, 0), "22:00", "07:00")).toBe(true);
    expect(isInDimWindow(minutes(12, 0), "22:00", "07:00")).toBe(false);
  });

  it("treats an equal start and end as never dimming", () => {
    expect(isInDimWindow(minutes(12, 0), "12:00", "12:00")).toBe(false);
  });
});
