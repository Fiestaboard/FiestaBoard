import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";
import type { Panel } from "@/lib/api";

import { server } from "./mocks/server";

const PANEL: Panel = {
  id: "abc123def456",
  short_code: 1,
  name: "Living Room TV",
  board_id: "vboard-1",
  screen_diagonal_inches: 55,
  calibration_scale: 1,
  animations_enabled: true,
  backdrop: "wall",
  auto_dim: { enabled: false, start: "22:00", end: "07:00" },
  created_at: "2026-08-25T00:00:00+00:00",
  updated_at: "2026-08-25T00:00:00+00:00",
  device_type: "note_array",
  board_missing: false,
  rows: 12,
  cols: 30,
};

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function mockList(panels: Panel[] = [PANEL]) {
  server.use(http.get("/api/panels", () => HttpResponse.json({ panels, total: panels.length })));
}

describe("FiestaPanelSettings", () => {
  it("lists panels with their short viewer URL and auto-fit grid", async () => {
    mockList();
    render(<FiestaPanelSettings />, { wrapper: Wrapper });
    expect(await screen.findByText("Living Room TV")).toBeInTheDocument();
    expect(screen.getByText(/\/p\/1$/)).toBeInTheDocument();
    expect(screen.getByText(/30 × 12 flaps/)).toBeInTheDocument();
  });

  it("creates a panel with the chosen screen size", async () => {
    mockList([]);
    let body: unknown;
    server.use(
      http.post("/api/panels", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ status: "success", panel: PANEL });
      }),
    );
    const user = userEvent.setup();
    render(<FiestaPanelSettings />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: "Create panel" }));
    await user.type(await screen.findByLabelText("Panel name"), "Kitchen TV");
    await user.click(screen.getByRole("button", { name: '65"' }));
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(body).toEqual({
        name: "Kitchen TV",
        screen_diagonal_inches: 65,
      }),
    );
  });

  it("deletes a panel after confirmation", async () => {
    mockList();
    let deleted = false;
    server.use(
      http.delete("/api/panels/abc123def456", () => {
        deleted = true;
        return HttpResponse.json({ status: "success" });
      }),
    );
    const user = userEvent.setup();
    render(<FiestaPanelSettings />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: "Delete panel" }));
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleted).toBe(true));
  });
});
