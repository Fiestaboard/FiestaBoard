import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import React from "react";
import { describe, expect, it } from "vitest";

import { AnimationSettings } from "@/components/settings/animation-settings";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { mockDisplaySettings } from "./mocks/handlers";
import { server } from "./mocks/server";

const API_BASE = "/api";

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

function withDisplaySettings(overrides: Partial<typeof mockDisplaySettings>) {
  server.use(
    http.get(`${API_BASE}/settings/all`, () =>
      HttpResponse.json({ display: { ...mockDisplaySettings, ...overrides } }),
    ),
  );
}

/** Capture the body of the next PUT /settings/display. */
function captureDisplayUpdate() {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.put(`${API_BASE}/settings/display`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      return HttpResponse.json({ status: "success", settings: { ...mockDisplaySettings, ...body } });
    }),
  );
  return bodies;
}

describe("AnimationSettings — board flip speed", () => {
  it("offers the four presets with the stored one selected", async () => {
    withDisplaySettings({ board_flap_speed: "quick" });
    render(<AnimationSettings />, { wrapper: TestWrapper });

    const group = await screen.findByRole("radiogroup", { name: "Flip speed" });
    const options = Array.from(group.querySelectorAll('[role="radio"]')).map((el) => el.textContent);
    expect(options).toEqual(["Hardware", "Quick", "Standard (default)", "Relaxed"]);

    await waitFor(() => {
      expect(screen.getByRole("radio", { name: "Quick" })).toHaveAttribute("aria-checked", "true");
    });
  });

  it("marks Standard as the default even when another preset is selected", async () => {
    // The per-preset hint below the group says "the default" — but only for
    // whichever preset is currently selected, so a user on Relaxed has no way
    // to tell which one they moved away from. The marker belongs on the option.
    withDisplaySettings({ board_flap_speed: "relaxed" });
    render(<AnimationSettings />, { wrapper: TestWrapper });

    const standard = await screen.findByRole("radio", { name: "Standard (default)" });
    expect(standard).toHaveAttribute("aria-checked", "false");
  });

  it("falls back to Standard when the stored value is a raw millisecond count", async () => {
    // The API's escape hatch has no radio of its own; showing nothing selected
    // or inventing a fifth option would both be worse than showing the default.
    withDisplaySettings({ board_flap_speed: 42 });
    render(<AnimationSettings />, { wrapper: TestWrapper });

    const standard = await screen.findByRole("radio", { name: "Standard (default)" });
    expect(standard).toHaveAttribute("aria-checked", "true");
  });

  it("persists the chosen preset to the display settings endpoint", async () => {
    const bodies = captureDisplayUpdate();
    const user = userEvent.setup();
    render(<AnimationSettings />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("radio", { name: "Relaxed" }));

    await waitFor(() => {
      expect(bodies).toContainEqual({ board_flap_speed: "relaxed" });
    });
  });

  it("says in so many words that this is the on-screen board, not the hardware", async () => {
    render(<AnimationSettings />, { wrapper: TestWrapper });

    // Users have a second, unrelated speed control under Behavior -> Board
    // transitions. Without this line the two read as the same setting twice.
    const note = await screen.findByText(/board preview on screen only/i);
    expect(note).toBeInTheDocument();
    expect(note.textContent).toMatch(/Board transitions/i);
  });

  it("replaces the preview with an explanation when board animations are off", async () => {
    withDisplaySettings({ board_animations: "off" });
    render(<AnimationSettings />, { wrapper: TestWrapper });

    expect(await screen.findByText(/Board animations are off, so flip speed has no effect/i)).toBeInTheDocument();
    expect(screen.queryByText("Preview")).not.toBeInTheDocument();
  });

  it("shows a live board to judge the cadence against", async () => {
    render(<AnimationSettings />, { wrapper: TestWrapper });

    expect(await screen.findByText("Preview")).toBeInTheDocument();
    // A real animated board, not a still image: it renders CharTiles.
    await waitFor(() => {
      expect(document.querySelector('[data-testid="char-tile-0-0"]')).not.toBeNull();
    });
  });
});
