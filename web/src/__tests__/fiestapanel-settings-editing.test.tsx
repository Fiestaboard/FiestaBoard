/**
 * FiestaPanel editor tests: the edit dialog (previously untested), the
 * calibration guard, the resize stale-reference warning, and the HDMI
 * install kickoff window.
 *
 * Sonner is mocked so toast calls can be asserted directly (there is no
 * <Toaster/> mounted in unit tests).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCollections, usePages } from "@/hooks/use-board";
import type { Panel } from "@/lib/api";

import { FIESTAPANEL_LED_MATRIX } from "./mocks/fiestapanel-models";
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

function mockList(
  panels: Panel[] = [PANEL],
  hdmi: object = { supported: false, status: "unsupported", enabled: null },
) {
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

function ContentNames() {
  const pages = usePages();
  const collections = useCollections();
  return (
    <>
      {pages.data?.pages.map((page) => (
        <span key={page.id}>{page.name}</span>
      ))}
      {collections.data?.collections.map((collection) => (
        <span key={collection.id}>{collection.name}</span>
      ))}
    </>
  );
}

describe("FiestaPanelSettings — edit dialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each([false, true])("converts legacy LED geometry explicitly with copy choice %s", async (copyContent) => {
    mockList([{ ...PANEL, render_style: "led_matrix", matrix_sizing: null }]);
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/panels/geometry", async ({ request }) => {
        const draft = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          rows: draft.matrix_layout === "screen" ? 13 : 12,
          cols: draft.matrix_layout === "screen" ? 32 : 30,
          geometry_key: String(draft.matrix_layout),
          device_model_spec: FIESTAPANEL_LED_MATRIX,
        });
      }),
      http.patch("/api/panels/abc123def456", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...PANEL, ...body });
      }),
    );
    server.use(
      http.get("/api/v1/pages", () => HttpResponse.json({ pages: [{ id: "copied-page", name: "Copied page" }] })),
      http.get("/api/v1/collections", () =>
        HttpResponse.json({ collections: [{ id: "copied-collection", name: "Copied collection" }] }),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["pages"], { pages: [] });
    client.setQueryData(["collections"], { collections: [] });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <FiestaPanelSettings />
        <ContentNames />
      </QueryClientProvider>,
    );
    await user.click(await screen.findByRole("button", { name: "Edit panel" }));
    expect(screen.getByRole("button", { name: "Keep existing grid" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Small (3 × 5)" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Fit screen shape" }));
    expect(await screen.findByText("32 × 13 characters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fill TV" })).toHaveAttribute("aria-pressed", "true");
    const copy = screen.getByRole("checkbox", { name: "Copy this panel’s content to the new grid" });
    expect(copy).not.toBeChecked();
    if (copyContent) await user.click(copy);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toMatchObject({ matrix_layout: "screen", matrix_sizing: "fill_tv" }));
    if (copyContent) {
      expect(body).toHaveProperty("copy_content", true);
      expect(await screen.findByText("Copied page")).toBeInTheDocument();
      expect(await screen.findByText("Copied collection")).toBeInTheDocument();
    } else expect(body).not.toHaveProperty("copy_content");
  });

  it("uses server text-size geometry and warns before copying into a smaller grid", async () => {
    mockList([
      { ...PANEL, render_style: "led_matrix", matrix_layout: "screen", matrix_font: "3x5", rows: 18, cols: 48 },
    ]);
    server.use(
      http.post("/api/panels/geometry", async ({ request }) => {
        const draft = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          rows: draft.matrix_font === "3x5" ? 18 : 13,
          cols: draft.matrix_font === "3x5" ? 48 : 32,
          geometry_key: String(draft.matrix_font),
          device_model_spec: FIESTAPANEL_LED_MATRIX,
        });
      }),
    );
    const user = userEvent.setup();
    await openEditDialog(user);
    expect(screen.queryByLabelText("Custom (inches)")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Large (5 × 7)" }));
    expect(await screen.findByText("32 × 13 characters")).toBeInTheDocument();
    expect(screen.getByText(/Content outside the new grid will be cropped/)).toBeInTheDocument();
  });

  it("shows a useful old-server fallback and blocks unsupported screen conversion", async () => {
    mockList([{ ...PANEL, render_style: "led_matrix" }]);
    const user = userEvent.setup();
    await openEditDialog(user);
    expect(await screen.findByText(/Draft geometry is unavailable on this server/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Fit screen shape" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("reports unsupported geometry before saving", async () => {
    mockList([{ ...PANEL, render_style: "led_matrix", matrix_layout: "screen" }]);
    server.use(
      http.post("/api/panels/geometry", () =>
        HttpResponse.json({ detail: "Screen aspect is too extreme" }, { status: 422 }),
      ),
    );
    await openEditDialog(userEvent.setup());
    expect(await screen.findByText("Screen aspect is too extreme")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("seeds the editor from the panel being edited", async () => {
    mockList();
    const user = userEvent.setup();
    await openEditDialog(user);

    expect(screen.getByLabelText("Panel name")).toHaveValue("Living Room TV");
    expect(screen.getByLabelText("Size calibration")).toHaveValue(1);
    expect(screen.getByRole("switch", { name: "Flip animation" })).toBeChecked();
  });

  it("seeds the render style as split-flap for a panel from a server that predates it", async () => {
    mockList();
    const user = userEvent.setup();
    await openEditDialog(user);
    expect(screen.getByRole("button", { name: "Split-flap" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "LED matrix" })).toHaveAttribute("aria-pressed", "false");
  });

  it("saves the chosen render style", async () => {
    mockList();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/panels/abc123def456", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...PANEL, render_style: "led_matrix", incompatible_references: null });
      }),
    );
    const user = userEvent.setup();
    await openEditDialog(user);
    await user.click(screen.getByRole("button", { name: "LED matrix" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body!.render_style).toBe("led_matrix");
  });

  it("shows sizing only for matrices and saves physical LED spacing", async () => {
    mockList();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/panels/abc123def456", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...PANEL, ...body });
      }),
    );
    const user = userEvent.setup();
    await openEditDialog(user);
    expect(screen.queryByRole("button", { name: "True LED size" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "LED matrix" }));
    expect(screen.getByRole("button", { name: "Fill TV" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "True LED size" }));
    fireEvent.change(screen.getByLabelText("LED spacing (mm)"), { target: { value: "0" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("LED spacing (mm)"), { target: { value: "5" } });
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ matrix_sizing: "true_size", matrix_pitch_mm: 5 });
  });

  it("allows saving after leaving an invalid hidden physical spacing", async () => {
    mockList([{ ...PANEL, render_style: "led_matrix", matrix_sizing: "true_size", matrix_pitch_mm: 4 }]);
    const user = userEvent.setup();
    await openEditDialog(user);
    fireEvent.change(screen.getByLabelText("LED spacing (mm)"), { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Fill TV" }));
    expect(screen.queryByLabelText("LED spacing (mm)")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("restores a matrix panel's saved sizing", async () => {
    mockList([{ ...PANEL, render_style: "led_matrix", matrix_sizing: "true_size", matrix_pitch_mm: 4 }]);
    await openEditDialog(userEvent.setup());
    expect(screen.getByRole("button", { name: "True LED size" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("LED spacing (mm)")).toHaveValue(4);
  });

  it("renames a legacy matrix without changing viewer defaults or other settings", async () => {
    mockList([{ ...PANEL, render_style: "led_matrix", matrix_sizing: null }]);
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/panels/abc123def456", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...PANEL, ...body });
      }),
    );
    const user = userEvent.setup();
    await openEditDialog(user);
    fireEvent.change(screen.getByLabelText("Panel name"), { target: { value: "Renamed" } });
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toEqual({ name: "Renamed" }));
  });

  it("previews server geometry without resizing legacy LED content when inches change", async () => {
    mockList([{ ...PANEL, render_style: "led_matrix", matrix_sizing: "fit_panel" }]);
    server.use(
      http.post("/api/panels/geometry", () =>
        HttpResponse.json({
          rows: 12,
          cols: 30,
          geometry_key: "legacy",
          device_model_spec: {
            ...FIESTAPANEL_LED_MATRIX,
            geometry: { kind: "pixels", width: 180, height: 96 },
          },
        }),
      ),
    );

    const user = userEvent.setup();
    const dialog = await openEditDialog(user);
    expect(await within(dialog).findByTestId("panel-matrix")).toHaveAttribute("data-sizing", "fit_panel");
    await user.click(screen.getByRole("button", { name: "True LED size" }));
    fireEvent.change(screen.getByLabelText("LED spacing (mm)"), { target: { value: "5" } });
    await user.click(screen.getByRole("button", { name: '75"' }));
    expect(within(dialog).getByTestId("panel-matrix")).toHaveAttribute("data-sizing", "true_size");
    const matrix = dialog.querySelector('[data-slot="led-matrix-display"]');
    expect(matrix).toHaveAttribute("data-matrix-width", "180");
    expect(matrix).toHaveAttribute("data-matrix-height", "96");
    expect(within(dialog).queryByTestId("tv-preview-grid")).not.toBeInTheDocument();
  });

  it("shows each panel's live board on its TV", async () => {
    mockList();
    server.use(
      http.get("/api/panel/abc123def456", () =>
        HttpResponse.json({ ...PANEL, board_color: "black", code62_glyph: "heart" }),
      ),
      http.get("/api/panel/abc123def456/frame", () =>
        HttpResponse.json({ characters: null, message: "LIVE NOW", rows: 12, cols: 30, updated_at: null }),
      ),
    );
    render(<FiestaPanelSettings />, { wrapper: Wrapper });
    const preview = await screen.findByTestId("panel-live-preview-abc123def456");
    await waitFor(() => expect(preview.querySelector('[data-slot="tv-frame"]')).toBeInTheDocument());
    await waitFor(() =>
      expect(preview.querySelector('[role="img"]')?.getAttribute("aria-label")).toContain("LIVE NOW"),
    );
  });

  it("blocks Save on an out-of-range calibration and shows the range", async () => {
    mockList();
    let patched = false;
    server.use(
      http.patch("/api/panels/abc123def456", () => {
        patched = true;
        return HttpResponse.json({ ...PANEL, incompatible_references: null });
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
          ...PANEL,
          screen_diagonal_inches: 85,
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
        return HttpResponse.json({ ...PANEL, incompatible_references: null });
      }),
    );
    const user = userEvent.setup();
    await openEditDialog(user);

    // 55" 16:9 auto-fits 29 × 12 characters (fit per character, not in
    // whole Note blocks)…
    expect(screen.getByTestId("tv-preview-meta")).toHaveTextContent("29 × 12 flaps at life size");
    expect(screen.getByTestId("tv-preview-grid")).toHaveAttribute("data-cols", "29");
    expect(screen.getByTestId("tv-preview-grid")).toHaveAttribute("data-rows", "12");

    // …and the same TV declared 21:9 fits 30 × 9, live.
    await user.click(screen.getByRole("button", { name: "21:9" }));
    expect(screen.getByTestId("tv-preview-meta")).toHaveTextContent("30 × 9 flaps at life size");
    expect(screen.getByTestId("tv-preview-grid")).toHaveAttribute("data-cols", "30");
    expect(screen.getByTestId("tv-preview-grid")).toHaveAttribute("data-rows", "9");

    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.screen_aspect_w).toBe(21);
    expect(patchBody).not.toHaveProperty("screen_aspect_h");
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
        HttpResponse.json({ ...PANEL, name: "Lounge TV", incompatible_references: null }),
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
    mockList([PANEL], { supported: true, status: "disabled", enabled: false });
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
