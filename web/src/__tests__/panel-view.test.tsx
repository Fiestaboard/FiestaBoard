import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { isInDimWindow } from "@/components/panel/panel-view";
import { PanelView } from "@/components/panel/panel-view";
import type { PanelFrame, PanelPublicConfig } from "@/lib/api";

import { FIESTAPANEL_LED_MATRIX } from "./mocks/fiestapanel-models";
import { server } from "./mocks/server";

const CONFIG: PanelPublicConfig = {
  id: "p1",
  short_code: 1,
  name: "Living Room TV",
  board_id: "vboard-1",
  screen_diagonal_inches: 55,
  calibration_scale: 1,
  animations_enabled: true,
  is_display: false,
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

  it("passes the panel's animation setting to the board", async () => {
    mockPanel({ ...CONFIG, animations_enabled: false });
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    expect(screen.getByTestId("panel-board-scaler")).toHaveAttribute("data-animations", "false");
  });

  it("shows the choose-a-display state on the reserved display URL", async () => {
    server.use(
      http.get("/api/panel/display", () => HttpResponse.json({ detail: "No display panel selected" }, { status: 404 })),
      http.get("/api/panel/display/frame", () =>
        HttpResponse.json({ detail: "No display panel selected" }, { status: 404 }),
      ),
    );
    render(<PanelView panelId="display" />, { wrapper: Wrapper });
    expect(await screen.findByText("No panel is set as the display output")).toBeInTheDocument();
  });

  it("draws a panel board at its per-character grid", async () => {
    // A 55" TV fits 12 × 29 characters — not a whole number of Notes.
    mockPanel({ ...CONFIG, device_type: "panel", rows: 12, cols: 29, notes_wide: null, notes_tall: null });
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    expect(screen.getByTestId("char-tile-11-28")).toBeInTheDocument();
    expect(screen.queryByTestId("char-tile-12-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("char-tile-0-29")).not.toBeInTheDocument();
  });

  it("still draws a legacy note-array panel at its Note grid", async () => {
    mockPanel();
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    expect(screen.getByTestId("char-tile-5-29")).toBeInTheDocument();
    expect(screen.queryByTestId("char-tile-6-0")).not.toBeInTheDocument();
  });

  it("draws only the flaps: the board has no housing of its own on the TV", async () => {
    mockPanel();
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    const board = await screen.findByRole("img");
    expect(board).toHaveAttribute("data-bezel", "false");
  });

  it("draws an LED-matrix panel through its model, not as flaps", async () => {
    mockPanel(
      {
        ...CONFIG,
        device_type: "panel",
        rows: 12,
        cols: 29,
        render_style: "led_matrix",
        device_model: "fiestapanel_led_matrix",
        device_model_spec: FIESTAPANEL_LED_MATRIX,
      },
      { ...FRAME, rows: 12, cols: 29 },
    );
    const { container } = render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    expect(container.querySelector('[data-slot="display-preview"]')).toHaveAttribute("data-technology", "led_matrix");
    expect(screen.queryByTestId("char-tile-0-0")).not.toBeInTheDocument();
  });

  it("draws the frame's rich cells when the frame has them", async () => {
    const cells = [[..."CELLS"].map((value) => ({ type: "char" as const, value }))];
    mockPanel(CONFIG, { ...FRAME, message: "IGNORED", cells });
    render(<PanelView panelId="p1" />, { wrapper: Wrapper });
    const board = await screen.findByRole("img");
    await waitFor(() => expect(board.getAttribute("aria-label")).toContain("CELLS"));
    expect(board.getAttribute("aria-label")).not.toContain("IGNORED");
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
