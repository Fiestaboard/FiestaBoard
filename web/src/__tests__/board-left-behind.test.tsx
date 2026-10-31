/**
 * A display's settings after a size change (design section 7): pages the
 * resize left behind are listed with their reason, not only toasted, and an
 * LED board that can draw more than one text size says what its Text size
 * setting now means — the size new pages start at — and that pages at the
 * other size change with Fade.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { DisplayEditor } from "@/components/displays/display-editor";
import type { OutputSummary } from "@/lib/api";

import { mockOutputs } from "./mocks/handlers";
import { server } from "./mocks/server";

const API = "/api";

const ARRAY = {
  id: "a",
  name: "Array",
  device_type: "note_array",
  notes_wide: 2,
  notes_tall: 1,
  output: "vestaboard",
  output_config: { api_mode: "cloud", note_array_token: "***" },
};

const FONT_OUTPUT: OutputSummary = {
  id: "acme_sign",
  name: "Acme Sign",
  description: "An LED sign on your network.",
  icon: "lightbulb",
  builtin: true,
  beta_gated: false,
  available: true,
  output_api: 1,
  capabilities: {
    technology: "led_matrix",
    delivery: "push",
    animation: "stream",
    native_transitions: [],
    charset: null,
  },
  device_models: [{ id: "divoom_pixoo64", label: "Divoom Pixoo 64" }],
  settings_schema: {
    type: "object",
    properties: {
      host: { type: "string", title: "Sign address" },
      font: { type: "string", title: "Text size", enum: ["5x7", "3x5"], enumNames: ["Large", "Small"] },
    },
    required: ["host"],
  },
  actions: [],
};

const PIXOO = {
  id: "pixoo",
  name: "Kitchen sign",
  device_type: "panel",
  output: "acme_sign",
  device_model: "divoom_pixoo64",
  grid_rows: 8,
  grid_cols: 10,
  output_config: { host: "192.0.2.50", font: "5x7" },
  producible_grids: { "5x7": [8, 10], "3x5": [10, 16] },
};

function respondWith(boards: Record<string, unknown>[], extra: Record<string, unknown> = {}) {
  const calls = { put: 0 };
  server.use(
    http.get(`${API}/outputs`, () => HttpResponse.json([...mockOutputs, FONT_OUTPUT])),
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards, devices: [] })),
    http.put(`${API}/settings/board`, () => {
      calls.put += 1;
      return HttpResponse.json({ board_type: "black", boards, devices: [], ...extra });
    }),
    http.get(`${API}/panels`, () => HttpResponse.json({ panels: [] })),
  );
  return calls;
}

function renderEditor(boardId: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DisplayEditor boardId={boardId} />
    </QueryClientProvider>,
  );
}

async function rename(name: string) {
  const input = await screen.findByTestId("board-name-input");
  await userEvent.clear(input);
  await userEvent.type(input, name);
  await userEvent.tab();
}

const TRANSIT_LEFT_BEHIND = {
  board_id: "a",
  board_name: "Array",
  page_id: "p1",
  page_name: "Transit",
  page_size: "note_array:3x30",
  reason: "Made for a 3×30 board",
};

describe("pages a resize left behind", () => {
  it("lists pages a resize left behind, with each reason", async () => {
    respondWith([ARRAY], {
      retargeted_pages: [],
      incompatible_references: [],
      left_behind_pages: [TRANSIT_LEFT_BEHIND],
    });
    renderEditor("a");
    await rename("Hall array");
    expect(await screen.findByRole("region", { name: "Pages this display no longer shows" })).toHaveTextContent(
      "Transit — Made for a 3×30 board",
    );
  });

  it("links each page left behind to its editor", async () => {
    respondWith([ARRAY], {
      retargeted_pages: [],
      incompatible_references: [],
      left_behind_pages: [TRANSIT_LEFT_BEHIND],
    });
    renderEditor("a");
    await rename("Hall array");
    const region = await screen.findByRole("region", { name: "Pages this display no longer shows" });
    expect(within(region).getByRole("link", { name: "Transit" })).toHaveAttribute("href", "/pages/edit/p1");
  });

  it("lists only this display's pages", async () => {
    const calls = respondWith([ARRAY], {
      retargeted_pages: [],
      incompatible_references: [],
      left_behind_pages: [{ ...TRANSIT_LEFT_BEHIND, board_id: "other", board_name: "Other" }],
    });
    renderEditor("a");
    await rename("Hall array");
    await waitFor(() => expect(calls.put).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("region", { name: "Pages this display no longer shows" })).not.toBeInTheDocument();
  });

  it("keeps the list through a later save that resized nothing", async () => {
    const calls = respondWith([ARRAY], {
      retargeted_pages: [],
      incompatible_references: [],
      left_behind_pages: [TRANSIT_LEFT_BEHIND],
    });
    renderEditor("a");
    await rename("Hall array");
    await screen.findByRole("region", { name: "Pages this display no longer shows" });
    respondWith([ARRAY], { retargeted_pages: [], incompatible_references: [], left_behind_pages: [] });
    await rename("Hall array 2");
    await waitFor(() => expect(calls.put).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole("region", { name: "Pages this display no longer shows" })).toHaveTextContent("Transit");
  });

  it("clears the list when a later resize leaves nothing behind", async () => {
    respondWith([ARRAY], {
      retargeted_pages: [],
      incompatible_references: [],
      left_behind_pages: [TRANSIT_LEFT_BEHIND],
    });
    renderEditor("a");
    await rename("Hall array");
    await screen.findByRole("region", { name: "Pages this display no longer shows" });
    // The display goes back to 3 notes wide: the save answers its new shape
    // and leaves nothing behind.
    respondWith([{ ...ARRAY, notes_wide: 3 }], {
      retargeted_pages: [],
      incompatible_references: [],
      left_behind_pages: [],
    });
    await rename("Hall array 2");
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Pages this display no longer shows" })).not.toBeInTheDocument(),
    );
  });

  it("shows no list when a save left nothing behind", async () => {
    const calls = respondWith([ARRAY], { retargeted_pages: [], incompatible_references: [], left_behind_pages: [] });
    renderEditor("a");
    await rename("Hall array");
    await waitFor(() => expect(calls.put).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("region", { name: "Pages this display no longer shows" })).not.toBeInTheDocument();
  });
});

describe("an LED board with more than one text size", () => {
  it("says Text size is the size new pages start at", async () => {
    respondWith([PIXOO]);
    renderEditor("pixoo");
    expect(
      await screen.findByText(
        "The size new pages start at. Pages made at the other size still show, at their own size.",
      ),
    ).toBeInTheDocument();
  });

  it("notes that pages at another text size use Fade", async () => {
    respondWith([PIXOO]);
    renderEditor("pixoo");
    expect(
      await screen.findByText(
        "Pages at the other text size change with Fade. Flip, Cascade and transition plugins need the display's own text size.",
      ),
    ).toBeInTheDocument();
  });

  it("says neither on a board with one text size", async () => {
    respondWith([{ ...PIXOO, producible_grids: null }]);
    renderEditor("pixoo");
    expect(await screen.findByLabelText(/Sign address/)).toBeInTheDocument();
    expect(screen.queryByText(/The size new pages start at/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Pages at the other text size change with Fade/)).not.toBeInTheDocument();
  });
});
