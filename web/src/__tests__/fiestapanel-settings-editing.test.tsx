/**
 * FiestaPanel editor tests: the edit dialog (previously untested), the
 * calibration guard, the resize stale-reference warning, and the HDMI
 * install kickoff window.
 *
 * Sonner is mocked so toast calls can be asserted directly (there is no
 * <Toaster/> mounted in unit tests).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Panel } from "@/lib/api";

import { server } from "./mocks/server";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), loading: vi.fn() },
  Toaster: () => null,
}));

// Must import after mocking sonner.
import { toast } from "sonner";

import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";

const PANEL: Panel = {
  id: "abc123def456",
  short_code: 1,
  name: "Living Room TV",
  board_id: "vboard-1",
  screen_diagonal_inches: 55,
  screen_aspect_w: 16,
  screen_aspect_h: 9,
  calibration_scale: 1,
  animations_enabled: true,
  is_display: false,
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function mockList(panels: Panel[] = [PANEL], hdmi: object = { supported: false, status: "unsupported" }) {
  server.use(
    http.get("/api/panels", () => HttpResponse.json({ panels, total: panels.length })),
    http.get("/api/settings/hdmi-kiosk", () => HttpResponse.json(hdmi)),
  );
}

async function openEditDialog(user: ReturnType<typeof userEvent.setup>) {
  render(<FiestaPanelSettings />, { wrapper: Wrapper });
  await user.click(await screen.findByRole("button", { name: "Edit panel" }));
  return screen.findByRole("dialog");
}

describe("FiestaPanelSettings — edit dialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("seeds the editor from the panel being edited", async () => {
    mockList();
    const user = userEvent.setup();
    await openEditDialog(user);

    expect(screen.getByLabelText("Panel name")).toHaveValue("Living Room TV");
    expect(screen.getByLabelText("Size calibration")).toHaveValue(1);
    expect(screen.getByRole("switch", { name: "Flip animation" })).toBeChecked();
  });

  it("blocks Save on an out-of-range calibration and shows the range", async () => {
    mockList();
    let patched = false;
    server.use(
      http.patch("/api/panels/abc123def456", () => {
        patched = true;
        return HttpResponse.json({ status: "success", panel: PANEL });
      }),
    );
    const user = userEvent.setup();
    await openEditDialog(user);

    // Clearing the field coerces to 0 (Number("") === 0) — that too must
    // block the save instead of PATCHing a value the backend 422s on.
    fireEvent.change(screen.getByLabelText("Size calibration"), { target: { value: "2" } });
    expect(await screen.findByText("Must be between 0.85 and 1.15.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Size calibration"), { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(patched).toBe(false);

    // Back in range: the error clears and Save re-enables.
    fireEvent.change(screen.getByLabelText("Size calibration"), { target: { value: "1.05" } });
    expect(screen.queryByText("Must be between 0.85 and 1.15.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("warns which pages no longer fit after a TV-size change", async () => {
    mockList();
    server.use(
      http.patch("/api/panels/abc123def456", () =>
        HttpResponse.json({
          status: "success",
          panel: { ...PANEL, screen_diagonal_inches: 85 },
          incompatible_references: [
            { page_id: "p1", page_name: "Morning Board", surface: "schedule", schedule_id: "s1" },
            { page_id: "p1", page_name: "Morning Board", surface: "active_page", schedule_id: null },
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    await openEditDialog(user);

    await user.click(screen.getByRole("button", { name: '85"' }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(toast.warning).toHaveBeenCalledTimes(1));
    // Page names are deduplicated across surfaces.
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining("Morning Board"), expect.anything());
    const message = vi.mocked(toast.warning).mock.calls[0][0] as string;
    expect(message.match(/Morning Board/g)).toHaveLength(1);
  });

  it("previews the aspect-ratio grid live and sends the aspect on save", async () => {
    mockList();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/panels/abc123def456", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ status: "success", panel: PANEL });
      }),
    );
    const user = userEvent.setup();
    await openEditDialog(user);

    // 55" 16:9 auto-fits 1×4 Note blocks (15 × 12 flaps)…
    expect(screen.getByTestId("tv-preview-meta")).toHaveTextContent("15 × 12 flaps · 1 × 4 Note blocks");
    expect(screen.getAllByTestId("tv-preview-block")).toHaveLength(4);

    // …and the same TV declared 21:9 fits 2×3 (30 × 9 flaps), live.
    await user.click(screen.getByRole("button", { name: "21:9" }));
    expect(screen.getByTestId("tv-preview-meta")).toHaveTextContent("30 × 9 flaps · 2 × 3 Note blocks");
    expect(screen.getAllByTestId("tv-preview-block")).toHaveLength(6);

    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.screen_aspect_w).toBe(21);
    expect(patchBody!.screen_aspect_h).toBe(9);
  });

  it("accepts a 3 inch pocket screen but not less", async () => {
    mockList();
    const user = userEvent.setup();
    await openEditDialog(user);

    fireEvent.change(screen.getByLabelText("Custom (inches)"), { target: { value: "3" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    fireEvent.change(screen.getByLabelText("Custom (inches)"), { target: { value: "2" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("does not warn when a save changes nothing size-related", async () => {
    mockList();
    server.use(
      http.patch("/api/panels/abc123def456", () =>
        HttpResponse.json({ status: "success", panel: { ...PANEL, name: "Lounge TV" } }),
      ),
    );
    const user = userEvent.setup();
    await openEditDialog(user);

    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.warning).not.toHaveBeenCalled();
  });
});

describe("FiestaPanelSettings — HDMI install kickoff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps showing install progress when the status flip lags the toggle", async () => {
    // The sidecar responds "queued" but the status query still reports
    // "disabled" for a while (apt install hasn't started). The switch must
    // not snap back to off with the install running invisibly.
    mockList([PANEL], { supported: true, status: "disabled" });
    server.use(
      http.post("/api/settings/hdmi-kiosk", () => HttpResponse.json({ status: "queued", action: "hdmi_enable" })),
    );
    const user = userEvent.setup();
    render(<FiestaPanelSettings />, { wrapper: Wrapper });

    const hdmiSwitch = await screen.findByRole("switch", { name: "HDMI output on this FiestaPi" });
    expect(hdmiSwitch).not.toBeChecked();
    await user.click(hdmiSwitch);

    // Post-toggle refetch still returns "disabled" — the kickoff window
    // keeps the switch on and the installing copy visible.
    await waitFor(() => expect(hdmiSwitch).toBeChecked());
    expect(await screen.findByText(/Setting up the HDMI kiosk/)).toBeInTheDocument();
  });
});
