import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";
import type { Panel } from "@/lib/api";

import { server } from "./mocks/server";

const PANEL: Panel = {
  id: "selected-panel",
  board_id: "selected-board",
  short_code: 7,
  name: "Example TV",
  screen_diagonal_inches: 55,
  screen_aspect_w: 16,
  screen_aspect_h: 9,
  render_style: "split_flap",
  calibration_scale: 1,
  animations_enabled: false,
  is_display: false,
  backdrop: "wall",
  auto_dim: { enabled: false, start: "22:00", end: "07:00" },
  created_at: "2026-11-13T00:00:00Z",
  updated_at: "2026-11-13T00:00:00Z",
  device_type: "note_array",
  board_missing: false,
  rows: 12,
  cols: 30,
};
let selected: Panel;
let requests: { id: string; body: Record<string, unknown> }[];

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}
    >
      {children}
    </QueryClientProvider>
  );
}

beforeEach(() => {
  selected = structuredClone(PANEL);
  requests = [];
  server.use(
    http.get("/api/panels", () =>
      HttpResponse.json({
        panels: [{ ...PANEL, id: "other-panel", board_id: "other-board", name: "Other TV" }, selected],
        total: 2,
      }),
    ),
    http.get("/api/settings/hdmi-kiosk", () => HttpResponse.json({ supported: false, status: "unsupported" })),
    http.get("/api/panel/:id", () => HttpResponse.json({ ...selected, board_color: "black", code62_glyph: "degree" })),
    http.get("/api/panel/:id/frame", () => HttpResponse.json({ message: null })),
    http.patch("/api/panels/:id", async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      requests.push({ id: String(params.id), body });
      selected = { ...selected, ...body } as Panel;
      return HttpResponse.json({ ...selected, incompatible_references: null });
    }),
  );
});

it("shows selected display controls inline without requiring an edit dialog", async () => {
  render(<FiestaPanelSettings boardId="selected-board" />, { wrapper: Wrapper });
  expect(await screen.findByLabelText("Panel name")).toHaveValue("Example TV");
  expect(screen.getByLabelText("Panel URL")).toHaveValue(`${window.location.origin}/p/7`);
  expect(screen.getByRole("radiogroup", { name: "TV size" })).toBeInTheDocument();
  expect(screen.getByRole("radiogroup", { name: "Render style" })).toBeInTheDocument();
  expect(screen.getByRole("switch", { name: "Auto-dim at night" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  expect(screen.queryByText("Other TV")).not.toBeInTheDocument();
});

it("applies TV size immediately to only the selected panel", async () => {
  render(<FiestaPanelSettings boardId="selected-board" />, { wrapper: Wrapper });
  await userEvent.click(await screen.findByRole("radio", { name: '65"' }));
  await waitFor(() => expect(requests).toEqual([{ id: "selected-panel", body: { screen_diagonal_inches: 65 } }]));
  await waitFor(() => expect(screen.getByRole("radio", { name: '65"' })).toHaveAttribute("aria-checked", "true"));
});

it("applies render style without a Save step", async () => {
  render(<FiestaPanelSettings boardId="selected-board" />, { wrapper: Wrapper });
  await userEvent.click(await screen.findByRole("radio", { name: "LED matrix" }));
  await waitFor(() => expect(requests).toEqual([{ id: "selected-panel", body: { render_style: "led_matrix" } }]));
});

it("preserves dim times when toggling auto-dim immediately", async () => {
  render(<FiestaPanelSettings boardId="selected-board" />, { wrapper: Wrapper });
  await userEvent.click(await screen.findByRole("switch", { name: "Auto-dim at night" }));
  await waitFor(() =>
    expect(requests).toEqual([
      { id: "selected-panel", body: { auto_dim: { enabled: true, start: "22:00", end: "07:00" } } },
    ]),
  );
});

it("commits a trimmed name when the inline field loses focus", async () => {
  render(<FiestaPanelSettings boardId="selected-board" />, { wrapper: Wrapper });
  const input = await screen.findByLabelText("Panel name");
  fireEvent.change(input, { target: { value: "  Renamed TV  " } });
  fireEvent.blur(input);
  await waitFor(() => expect(requests).toEqual([{ id: "selected-panel", body: { name: "Renamed TV" } }]));
});

it("disables settings while saving and restores the stored choice after an error", async () => {
  let respond!: () => void;
  const pending = new Promise<void>((resolve) => {
    respond = resolve;
  });
  server.use(
    http.patch("/api/panels/:id", async () => {
      await pending;
      return HttpResponse.json({ detail: "Example save failed" }, { status: 503 });
    }),
  );
  render(<FiestaPanelSettings boardId="selected-board" />, { wrapper: Wrapper });
  await userEvent.click(await screen.findByRole("radio", { name: '65"' }));
  expect(screen.getByRole("switch", { name: "Auto-dim at night" })).toBeDisabled();
  expect(screen.getByText("Saving...")).toHaveAttribute("role", "status");
  respond();
  expect(await screen.findByRole("alert")).toHaveTextContent("Example save failed");
  await waitFor(() => expect(screen.getByRole("radio", { name: '55"' })).toHaveAttribute("aria-checked", "true"));
  expect(screen.getByRole("switch", { name: "Auto-dim at night" })).toBeEnabled();
});

it("removes only the selected panel after the existing confirmation", async () => {
  const deleted: string[] = [];
  const onDeleted = vi.fn();
  server.use(
    http.delete("/api/panels/:id", ({ params }) => {
      deleted.push(String(params.id));
      return HttpResponse.json({ id: params.id });
    }),
  );
  render(<FiestaPanelSettings boardId="selected-board" onDeleted={onDeleted} />, { wrapper: Wrapper });
  await userEvent.click(await screen.findByRole("button", { name: "Remove display…" }));
  expect(deleted).toEqual([]);
  await userEvent.click(screen.getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(deleted).toEqual(["selected-panel"]));
  await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
});

it("uses the supplied viewport preview and updates its size heading immediately", async () => {
  render(<FiestaPanelSettings boardId="selected-board" preview={<div>Actual-size board viewport</div>} />, {
    wrapper: Wrapper,
  });
  expect(await screen.findByText("Actual-size board viewport")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("radio", { name: '65"' }));
  expect(await screen.findByText("Preview at 65″")).toBeInTheDocument();
});

it("saves a valid custom diagonal on blur without submitting an invalid size", async () => {
  render(<FiestaPanelSettings boardId="selected-board" />, { wrapper: Wrapper });
  await userEvent.click(await screen.findByRole("radio", { name: "Custom (inches)" }));
  const size = screen.getByRole("spinbutton", { name: "Custom (inches)" });
  fireEvent.change(size, { target: { value: "0" } });
  fireEvent.blur(size);
  expect(size).toHaveAttribute("aria-invalid", "true");
  expect(requests).toEqual([]);
  fireEvent.change(size, { target: { value: "72.5" } });
  fireEvent.blur(size);
  await waitFor(() => expect(requests).toEqual([{ id: "selected-panel", body: { screen_diagonal_inches: 72.5 } }]));
});
