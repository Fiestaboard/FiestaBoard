import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import React from "react";
import { describe, expect, it } from "vitest";

import { BoardSettings } from "@/components/settings/board-settings";

import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function withBoardConfig(config: Record<string, unknown>) {
  server.use(http.get(`${API_BASE}/config/board`, () => HttpResponse.json({ config, api_modes: ["local", "cloud"] })));
}

/**
 * BoardSettings seeded its form from GET /config/board in a useEffect — one of
 * the 42 `react-hooks/set-state-in-effect` warnings in #1568. It is now seeded
 * during render. The seeding is load-bearing beyond cosmetics: the card
 * auto-saves `formData` one second after `hasChanges` flips, so a form that
 * seeds late (or seeds and marks itself dirty) can PUT the wrong config back.
 */
describe("BoardSettings form seeding", () => {
  it("shows the saved board host once the config loads", async () => {
    withBoardConfig({ api_mode: "local", host: "192.168.1.100", local_api_key: "***" });
    render(<BoardSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("192.168.1.100")).toHaveValue("192.168.1.100");
    });
  });

  it("selects the saved connection mode once the config loads", async () => {
    withBoardConfig({ api_mode: "cloud", cloud_key: "***" });
    render(<BoardSettings />, { wrapper: TestWrapper });

    // The cloud-only field is what proves api_mode came from the server: the
    // component's own default for a missing api_mode is "local".
    expect(await screen.findByText("Read/Write API Key")).toBeInTheDocument();
  });

  it("does not mark the freshly seeded form as changed", async () => {
    // hasChanges drives a 1s debounced auto-save. Seeding must leave it false
    // or merely opening the card would PUT the config straight back.
    const puts: unknown[] = [];
    withBoardConfig({ api_mode: "local", host: "192.168.1.100", local_api_key: "***" });
    server.use(
      http.put(`${API_BASE}/config/board`, async ({ request }) => {
        puts.push(await request.json());
        return HttpResponse.json({ status: "success", config: {} });
      }),
    );

    render(<BoardSettings />, { wrapper: TestWrapper });
    await waitFor(() => {
      expect(screen.getByPlaceholderText("192.168.1.100")).toHaveValue("192.168.1.100");
    });

    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(puts).toEqual([]);
  });
});
