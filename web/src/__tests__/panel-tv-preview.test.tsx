/**
 * A panel's live preview in Settings → FiestaPanel: the board the TV is
 * showing, on FiestaUI's `TvFrame`, with the television drawn from the
 * panel's own settings and the viewer's state — `screen_diagonal_inches` →
 * `diagonalInches`, `screen_aspect_w`/`_h` → `aspect`, the auto-dim window
 * → `dimmed`, a failed frame fetch → `offline`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { PANEL_DIM_LEVEL, panelTvOptions, PanelTvPreview } from "@/components/panel/panel-tv-preview";
import type { PanelFrame, PanelPublicConfig } from "@/lib/api";

import { FIESTAPANEL_LED_MATRIX, FIESTAPANEL_SPLIT_FLAP } from "./mocks/fiestapanel-models";
import { server } from "./mocks/server";

const CONFIG: PanelPublicConfig = {
  id: "p1",
  short_code: 1,
  name: "Hall TV",
  board_id: "vboard-1",
  screen_diagonal_inches: 65,
  screen_aspect_w: 21,
  screen_aspect_h: 9,
  calibration_scale: 1,
  animations_enabled: false,
  is_display: false,
  backdrop: "wall",
  auto_dim: { enabled: false, start: "22:00", end: "07:00" },
  render_style: "split_flap",
  created_at: "2026-08-25T00:00:00+00:00",
  updated_at: "2026-08-25T00:00:00+00:00",
  device_type: "panel",
  board_missing: false,
  rows: 12,
  cols: 29,
  board_color: "black",
  code62_glyph: "heart",
  device_model: "fiestapanel_split_flap",
  device_model_spec: FIESTAPANEL_SPLIT_FLAP,
};

const FRAME: PanelFrame = { characters: null, message: "ON THE TV", rows: 12, cols: 29, updated_at: null };

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function mockPanel(config: PanelPublicConfig = CONFIG, frame: PanelFrame = FRAME) {
  server.use(
    http.get("/api/panel/p1", () => HttpResponse.json(config)),
    http.get("/api/panel/p1/frame", () => HttpResponse.json(frame)),
  );
}

describe("panelTvOptions", () => {
  it("draws the television from the panel's screen settings", () => {
    expect(panelTvOptions(CONFIG, { dimActive: false, offline: false })).toEqual({
      diagonalInches: 65,
      aspect: { w: 21, h: 9 },
      dimmed: 0,
      offline: false,
    });
  });

  it("falls back to 16:9 for a panel stored before the aspect existed", () => {
    const { screen_aspect_w: _w, screen_aspect_h: _h, ...legacy } = CONFIG;
    expect(panelTvOptions(legacy, { dimActive: false, offline: false }).aspect).toEqual({ w: 16, h: 9 });
  });

  it("dims the screen to the viewer's overlay level inside the auto-dim window", () => {
    expect(panelTvOptions(CONFIG, { dimActive: true, offline: false }).dimmed).toBe(PANEL_DIM_LEVEL);
  });

  it("turns the screen off when the frame cannot be fetched", () => {
    expect(panelTvOptions(CONFIG, { dimActive: false, offline: true }).offline).toBe(true);
  });
});

describe("PanelTvPreview", () => {
  it("frames the board on a TV of the panel's size and aspect", async () => {
    mockPanel();
    const { container } = render(<PanelTvPreview panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    const tv = container.querySelector('[data-slot="tv-frame"]');
    expect(tv).toHaveAttribute("data-diagonal", "65");
    expect(tv).toHaveAttribute("data-aspect", (21 / 9).toFixed(4));
    expect(tv).not.toHaveAttribute("data-offline");
  });

  it("draws a split-flap panel as bare flaps on the screen", async () => {
    mockPanel();
    render(<PanelTvPreview panelId="p1" />, { wrapper: Wrapper });
    const board = await screen.findByRole("img");
    expect(board).toHaveAttribute("data-bezel", "false");
    expect(board.getAttribute("aria-label")).toContain("ON THE TV");
  });

  it("draws an LED panel through its LED model", async () => {
    mockPanel({
      ...CONFIG,
      render_style: "led_matrix",
      device_model: "fiestapanel_led_matrix",
      device_model_spec: FIESTAPANEL_LED_MATRIX,
    });
    const { container } = render(<PanelTvPreview panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    expect(container.querySelector('[data-slot="display-preview"]')).toHaveAttribute("data-technology", "led_matrix");
  });

  it("dims the screen inside the panel's auto-dim window", async () => {
    mockPanel({ ...CONFIG, auto_dim: { enabled: true, start: "00:00", end: "23:59" } });
    const { container } = render(<PanelTvPreview panelId="p1" />, { wrapper: Wrapper });
    await screen.findByRole("img");
    expect(container.querySelector('[data-slot="tv-frame"]')).toHaveAttribute("data-dimmed", String(PANEL_DIM_LEVEL));
  });

  it("shows the screen off when the frame fetch fails", async () => {
    mockPanel();
    const { container } = render(<PanelTvPreview panelId="p1" frameIntervalMs={40} />, { wrapper: Wrapper });
    await screen.findByRole("img");
    server.use(http.get("/api/panel/p1/frame", () => HttpResponse.error()));
    await waitFor(() => expect(container.querySelector('[data-slot="tv-frame"]')).toHaveAttribute("data-offline"), {
      timeout: 5000,
    });
  });
});
