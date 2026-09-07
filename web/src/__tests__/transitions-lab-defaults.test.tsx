import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const { default: TransitionsLabPage } = await import("../../app/routes/transitions");

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const PLUGIN = {
  id: "wipe",
  name: "Wipe",
  description: "Wipes across",
  version: "1.0.0",
  enabled: true,
  config: { direction: "left" },
  config_schema: {},
};

const PAGES = [
  { id: "p1", name: "Weather", device_type: "note", type: "template", duration_seconds: 60 },
  { id: "p2", name: "Transit", device_type: "note", type: "template", duration_seconds: 60 },
];

/** Two frames so playback has somewhere to go, then somewhere to stop. */
const FRAMES = [
  { grid: [[0]], delay_ms: 10 },
  { grid: [[1]], delay_ms: 10 },
];

function mockLab() {
  server.use(
    http.get(`${API_BASE}/settings/beta`, () =>
      HttpResponse.json({ settings: { transition_plugins_enabled: true }, available: [] }),
    ),
    http.get(`${API_BASE}/transitions/plugins`, () => HttpResponse.json({ plugins: [PLUGIN] })),
    http.get(`${API_BASE}/pages`, () => HttpResponse.json({ pages: PAGES })),
    http.post(`${API_BASE}/transitions/preview`, () =>
      HttpResponse.json({ frames: FRAMES, frame_count: FRAMES.length, capped: false }),
    ),
  );
}

/**
 * The Transition Lab drove six separate `useEffect`s that wrote state — every
 * default on the page plus the whole playback state machine (6 of the 42
 * `react-hooks/set-state-in-effect` warnings in #1568). They are all
 * render-phase now, and none of them had a test.
 */
describe("Transition Lab defaults and playback", () => {
  beforeEach(mockLab);

  it("selects the first plugin once the plugin list loads", async () => {
    render(<TransitionsLabPage />, { wrapper: TestWrapper });

    const trigger = await screen.findByLabelText("Transition plugin");
    await waitFor(() => expect(trigger).toHaveTextContent("Wipe"));
  });

  it("defaults the from and to pickers to the first two pages", async () => {
    render(<TransitionsLabPage />, { wrapper: TestWrapper });

    const from = await screen.findByLabelText("From page");
    const to = await screen.findByLabelText("To page");
    await waitFor(() => expect(from).toHaveTextContent("Weather"));
    expect(to).toHaveTextContent("Transit");
  });

  it("seeds the config editor from the selected plugin's saved config", async () => {
    render(<TransitionsLabPage />, { wrapper: TestWrapper });

    const config = await screen.findByLabelText("Plugin config (JSON)");
    await waitFor(() => {
      expect((config as HTMLTextAreaElement).value).toBe(JSON.stringify({ direction: "left" }, null, 2));
    });
  });

  it("matches the preview canvas to the target page's device type", async () => {
    // Both pages are notes, so the device picker must follow rather than stay
    // on its "flagship" default.
    render(<TransitionsLabPage />, { wrapper: TestWrapper });

    const device = await screen.findByLabelText("Device");
    await waitFor(() => expect(device).toHaveTextContent("Note (3×15)"));
  });

  it("starts on frame 1 and stops on the last frame when a preview lands", async () => {
    const user = userEvent.setup();
    render(<TransitionsLabPage />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByLabelText("From page")).toHaveTextContent("Weather"));
    await user.click(screen.getByRole("button", { name: "Run preview" }));

    // Autoplay runs to the end, then stops: the toggle is back to "Play" and
    // the counter is parked on the last frame.
    await waitFor(() => expect(screen.getByText("Frame 2 / 2")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument());
  });
});
