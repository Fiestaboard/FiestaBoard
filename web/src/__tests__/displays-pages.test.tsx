/**
 * Displays (plan D21): the list (/displays) and one display's page
 * (/displays/:boardId) — live preview, output, state, quick actions,
 * the settings screen, the transition from the device's menu, and a
 * FiestaPanel's own controls.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DisplaysSection } from "../../app/routes/displays";
import DisplaysPage from "../../app/routes/displays._index";
import DisplayPage from "../../app/routes/displays.$boardId";
import { mockOutputs, mockStatus } from "./mocks/handlers";
import { server } from "./mocks/server";

const push = vi.fn();
const params: { boardId?: string } = {};
const originalMatchMedia = window.matchMedia;

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/displays",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

const API = "/api";

const KITCHEN = {
  id: "kitchen",
  name: "Kitchen",
  device_type: "flagship",
  board_color: "black",
  output: "vestaboard",
  output_config: { api_mode: "local", host: "192.0.2.10", local_api_key: "***" },
};
const DESK = {
  id: "desk",
  name: "Desk Pixoo",
  device_type: "panel",
  grid_rows: 8,
  grid_cols: 10,
  board_color: "black",
  output: "divoom_pixoo",
  device_model: "divoom_pixoo64",
  output_config: { host: "192.0.2.20" },
};
const TV = {
  id: "tv",
  name: "Living Room (Panel)",
  device_type: "panel",
  grid_rows: 12,
  grid_cols: 29,
  board_color: "black",
  output: "fiestapanel",
  output_config: {},
};

const PIXOO_OUTPUT = {
  id: "divoom_pixoo",
  name: "Divoom Pixoo",
  description: "A Pixoo on your network.",
  icon: "grid-3x3",
  builtin: false,
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
  device_models: [{ id: "divoom_pixoo64", label: "Pixoo 64" }],
  settings_schema: { type: "object", properties: { host: { type: "string", title: "Pixoo address" } } },
  actions: [],
};

function setup(boards: Record<string, unknown>[], status: Record<string, unknown> = {}) {
  const calls = { put: [] as { boards: Record<string, unknown>[] }[], pause: [] as unknown[], removed: [] as string[] };
  let stored = boards;
  server.use(
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards: stored, devices: [] })),
    http.put(`${API}/settings/board`, async ({ request }) => {
      const body = (await request.json()) as { boards: Record<string, unknown>[] };
      calls.put.push(body);
      stored = body.boards;
      return HttpResponse.json({ board_type: "black", boards: stored, devices: [] });
    }),
    http.delete(`${API}/settings/board/:board`, ({ params: p }) => {
      calls.removed.push(String(p.board));
      return HttpResponse.json({});
    }),
    http.get(`${API}/outputs`, () => HttpResponse.json([...mockOutputs, PIXOO_OUTPUT])),
    http.get(`${API}/v1/status`, () => HttpResponse.json({ ...mockStatus, boards: status })),
    http.patch(`${API}/v1/boards/:board`, async ({ request, params: p }) => {
      calls.pause.push({ board: p.board, ...((await request.json()) as object) });
      return HttpResponse.json({});
    }),
    http.get(`${API}/panels`, () =>
      HttpResponse.json({
        panels: [
          {
            id: "p1",
            short_code: 1,
            name: "Living Room",
            board_id: "tv",
            screen_diagonal_inches: 55,
            screen_aspect_w: 16,
            screen_aspect_h: 9,
            calibration_scale: 1,
            animations_enabled: false,
            is_display: false,
            auto_dim: { enabled: false, start: "22:00", end: "07:00" },
            rows: 12,
            cols: 29,
          },
          {
            id: "p2",
            short_code: 2,
            name: "Bedroom",
            board_id: "other",
            screen_diagonal_inches: 43,
            screen_aspect_w: 16,
            screen_aspect_h: 9,
            calibration_scale: 1,
            animations_enabled: false,
            is_display: false,
            auto_dim: { enabled: false, start: "22:00", end: "07:00" },
            rows: 10,
            cols: 24,
          },
        ],
        total: 2,
      }),
    ),
    http.get(`${API}/settings/hdmi-kiosk`, () =>
      HttpResponse.json({ supported: false, status: "unsupported", enabled: null }),
    ),
  );
  return calls;
}

function renderWith(node: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {node}
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  push.mockReset();
  delete params.boardId;
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

describe("/displays", () => {
  it.each([390, 768, 900])(
    "keeps the %ipx fleet concise without dropping accessible hardware or override timing",
    async (width) => {
      const media = originalMatchMedia("");
      window.matchMedia = vi.fn((query) => ({
        ...media,
        media: query,
        matches: query === "(max-width: 1023.98px)" || (query === "(max-width: 767.98px)" && width < 768),
      }));
      setup([KITCHEN, DESK], {
        kitchen: { configured: true, health: { reachable: true, breaker_open: false } },
        desk: { configured: true, health: { reachable: true, breaker_open: false } },
      });
      server.use(
        http.get(`${API}/v1/pages`, () =>
          HttpResponse.json({ pages: [{ id: "night", name: "Good night" }], total: 1 }),
        ),
        http.get(`${API}/v1/boards/:board`, ({ params: p }) =>
          HttpResponse.json({
            id: p.board,
            schedule_enabled: true,
            next_change_at: new Date(2099, 10, 17, 22).toISOString(),
            next_page_id: "night",
            override_expires_at: p.board === "desk" ? new Date(2099, 10, 17, 21).toISOString() : null,
          }),
        ),
      );
      renderWith(<DisplaysPage />);
      const cards = await screen.findAllByTestId("display-card");
      expect(await within(cards[0]).findByText("Then Good night", { exact: true })).toBeInTheDocument();
      expect(cards[0]).toHaveAttribute("data-layout", "inline");
      expect(within(cards[0]).getByRole("img", { name: "22 columns by 6 rows" })).toBeInTheDocument();
      expect(within(cards[0]).getByTestId("display-output").parentElement).toHaveClass("sr-only");
      const override = await within(cards[1]).findByText("Override", { exact: true });
      expect(override).toHaveAccessibleName(/^Override · until /);
      expect(within(cards[1]).getByText("Online", { exact: true })).toHaveClass("sr-only");
      expect(within(cards[1]).getByText("Holds until 9:00 PM, then Schedule resumes.", { exact: true })).toBeVisible();
    },
  );

  it("groups unreachable displays before healthy displays using words as well as dots", async () => {
    setup([KITCHEN, DESK], {
      kitchen: {
        configured: true,
        paused: false,
        active_page_id: null,
        health: { reachable: true, breaker_open: false },
      },
      desk: {
        configured: true,
        paused: false,
        active_page_id: null,
        health: { reachable: false, breaker_open: false },
      },
    });
    renderWith(<DisplaysPage />);
    const problems = await screen.findByRole("list", { name: "Needs a look" });
    expect(within(problems).getByText("Desk Pixoo")).toBeInTheDocument();
    expect(Array.from(problems.children).every((element) => element.tagName === "LI")).toBe(true);
    expect(within(problems).getByText("Can't reach")).toBeInTheDocument();
    const online = screen.getByRole("list", { name: "Online" });
    expect(within(online).getByText("Kitchen")).toBeInTheDocument();
    expect(problems.compareDocumentPosition(online) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("uses readable status text with a warning dot for a panel without a viewer", async () => {
    setup([TV]);
    server.use(http.get(`${API}/auth/sessions`, () => HttpResponse.json({ sessions: [], total: 0 })));
    renderWith(<DisplaysPage />);
    const group = await screen.findByRole("list", { name: "Needs a look" });
    expect(within(group).getByText("No viewer", { exact: true })).toHaveClass("text-hue-yellow");
    expect(group.querySelector('[data-slot="status-dot"]')).toHaveAttribute("data-status", "warning");
  });

  it("does not claim an unknown display is online", async () => {
    setup([KITCHEN]);
    renderWith(<DisplaysPage />);
    const list = await screen.findByRole("list", { name: "Other displays" });
    expect(within(list).getByText("Status unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Online" })).not.toBeInTheDocument();
  });

  it("keeps unknown and no-viewer states explicit in compact rows even with an override", async () => {
    const media = originalMatchMedia("");
    window.matchMedia = vi.fn((query) => ({
      ...media,
      media: query,
      matches: query === "(max-width: 1023.98px)" || query === "(max-width: 767.98px)",
    }));
    setup([KITCHEN, TV]);
    server.use(
      http.get(`${API}/auth/sessions`, () => HttpResponse.json({ sessions: [], total: 0 })),
      http.get(`${API}/v1/boards/:board`, ({ params: p }) =>
        HttpResponse.json({
          id: p.board,
          schedule_enabled: false,
          override_expires_at: new Date(2099, 10, 17, 21).toISOString(),
        }),
      ),
    );
    renderWith(<DisplaysPage />);
    await waitFor(() => expect(screen.getAllByText("Override", { exact: true })).toHaveLength(2));
    const unknown = screen.getByText("Status unavailable", { exact: true });
    const noViewer = screen.getByText("No viewer", { exact: true });
    expect(unknown).not.toHaveClass("sr-only");
    expect(noViewer).not.toHaveClass("sr-only");
    expect(screen.getByText("No signed-in TV is showing this display", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText("Override · until 9:00 PM", { exact: true })).toHaveLength(2);
    expect(screen.queryByText(/then Schedule resumes/)).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Online" })).not.toBeInTheDocument();
  });

  it("lists every display with its name, output and a way into its settings", async () => {
    setup([KITCHEN, DESK]);
    renderWith(<DisplaysPage />);
    const cards = await screen.findAllByTestId("display-card");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText("Kitchen")).toBeInTheDocument();
    await waitFor(() => expect(within(cards[0]).getByTestId("display-output")).toHaveTextContent("Vestaboard"));
    expect(within(cards[1]).getByTestId("display-output")).toHaveTextContent("Divoom Pixoo");
    expect(within(cards[0]).getByRole("img", { name: "22 columns by 6 rows" })).toHaveTextContent("22 × 6");
    expect(within(cards[1]).getByRole("img", { name: "10 columns by 8 rows, Panel" })).toHaveTextContent("10 × 8");
    expect(cards[1]).toHaveAttribute("href", "/displays/desk");
  });

  it("shows each display's status from the status poll", async () => {
    setup([KITCHEN, DESK], {
      kitchen: {
        configured: true,
        paused: false,
        active_page_id: null,
        output_status: { state: "connected", message: "" },
      },
      desk: {
        configured: false,
        paused: false,
        active_page_id: null,
        output_status: { state: "not_configured", message: "" },
      },
    });
    renderWith(<DisplaysPage />);
    const cards = await screen.findAllByTestId("display-card");
    expect(await screen.findByRole("list", { name: "Needs a look" })).toHaveTextContent("Not configured");
    expect(await screen.findByRole("list", { name: "Online" })).toHaveTextContent("Online");
  });

  it("draws an LED display as its LED matrix and a split-flap one as flaps", async () => {
    setup([KITCHEN, DESK]);
    renderWith(<DisplaysPage />);
    const cards = await screen.findAllByTestId("display-card");
    await userEvent.click(cards[1]);
    const pane = screen.getByTestId("display-detail-pane");
    await waitFor(() =>
      expect(pane.querySelector("[data-slot='display-preview']")).toHaveAttribute("data-model", "divoom_pixoo64"),
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("pauses the selected display from its overview", async () => {
    const calls = setup([KITCHEN]);
    renderWith(<DisplaysPage />);
    await userEvent.click(await screen.findByRole("switch", { name: "Pause display" }));
    await waitFor(() => expect(calls.pause).toEqual([{ board: "kitchen", paused: true }]));
  });

  it("shows the current page and health separately from the next change", async () => {
    setup([KITCHEN], {
      kitchen: {
        configured: true,
        paused: false,
        active_page_id: "current",
        health: { reachable: true, breaker_open: false, latency_ms: 42, last_connected_at: "2026-11-16T09:41:00Z" },
      },
    });
    server.use(
      http.get(`${API}/v1/pages`, () =>
        HttpResponse.json({ pages: [{ id: "current", name: "Evening commute" }], total: 1 }),
      ),
      http.get(`${API}/v1/boards/kitchen`, () =>
        HttpResponse.json({ id: "kitchen", resolved_page_id: "current", schedule_enabled: true }),
      ),
    );
    renderWith(<DisplaysPage />);
    const pane = await screen.findByTestId("display-detail-pane");
    expect(await within(pane).findByText("Now showing · Evening commute")).toBeInTheDocument();
    expect(within(pane).getByTestId("display-health-summary")).toHaveTextContent("42 ms");
  });

  it("compares actual and expected frames in Diagnostics when readback exists", async () => {
    setup([KITCHEN]);
    server.use(
      http.get(`${API}/board/current-message`, () =>
        HttpResponse.json({
          characters: [[1]],
          expected_characters: [[2]],
          message: "A",
          api_mode: "local",
          rows: 6,
          cols: 22,
        }),
      ),
    );
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Diagnostics" }));
    const comparison = await screen.findByTestId("display-frame-comparison");
    expect(within(comparison).getByText("What the board shows")).toBeInTheDocument();
    expect(within(comparison).getByText("What FiestaBoard sent")).toBeInTheDocument();
    expect(within(comparison).getAllByRole("img")).toHaveLength(2);
    expect(screen.getByTestId("display-diagnostics")).toHaveTextContent("Last error");
  });

  it("opens full-width diagnostics for the selected display", async () => {
    setup([KITCHEN]);
    renderWith(<DisplaysPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Diagnostics" }));
    expect(push).toHaveBeenCalledWith("/displays/kitchen?section=diagnostics");
  });

  it("opens diagnostics with this display's health evidence", async () => {
    setup([KITCHEN], {
      kitchen: {
        configured: true,
        paused: false,
        active_page_id: null,
        health: {
          reachable: false,
          breaker_open: false,
          latency_ms: 42,
          last_connected_at: null,
          last_update_at: null,
          last_error: "timeout",
        },
      },
    });
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Diagnostics" }));
    const diagnostics = await screen.findByTestId("display-diagnostics");
    expect(diagnostics).toHaveTextContent("42 ms");
    expect(diagnostics).toHaveTextContent("Can't reach");
    expect(diagnostics).toHaveTextContent("Last error");
  });

  it("offers Resume on a paused display", async () => {
    setup([{ ...KITCHEN, paused: true }]);
    renderWith(<DisplaysPage />);
    expect(await screen.findByRole("switch", { name: "Pause display" })).toBeChecked();
    expect(await screen.findByRole("list", { name: "Other displays" })).toHaveTextContent("Paused");
  });

  it("Add a display opens the output-first flow", async () => {
    setup([KITCHEN]);
    renderWith(
      <DisplaysSection>
        <DisplaysPage />
      </DisplaysSection>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Add a display" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a display" });
    expect(await within(dialog).findByRole("radio", { name: /Vestaboard/ })).toBeInTheDocument();
  });

  it("opens a newly added display's page", async () => {
    setup([KITCHEN]);
    server.use(
      http.post(`${API}/settings/board/add`, () =>
        HttpResponse.json({
          boards: [KITCHEN, { id: "new", name: "My board", device_type: "flagship", output: "vestaboard" }],
        }),
      ),
    );
    renderWith(
      <DisplaysSection>
        <DisplaysPage />
      </DisplaysSection>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Add a display" }));
    await userEvent.click(await screen.findByRole("radio", { name: /Vestaboard/ }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    server.use(
      http.post(`${API}/outputs/vestaboard/actions/test_connection`, () =>
        HttpResponse.json({
          status: "ok",
          message: "Board answered",
          guidance: [],
          fields: null,
          geometry: null,
          devices: null,
        }),
      ),
    );
    await userEvent.type(await screen.findByLabelText("Address"), "192.0.2.80");
    await userEvent.type(screen.getByLabelText("Local API key"), "test_key");
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add display" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Add display" }));
    // The default add mock answers with a board "new" appended.
    await waitFor(() => expect(push).toHaveBeenCalledWith("/displays/new"));
  });
});

describe("/displays section", () => {
  it("keeps Displays as the page heading and names the open display under a breadcrumb", async () => {
    setup([KITCHEN, DESK]);
    params.boardId = "kitchen";
    renderWith(
      <DisplaysSection>
        <DisplayPage />
      </DisplaysSection>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Displays" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "Kitchen" })).toBeInTheDocument();
    const trail = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(trail).getByRole("link", { name: "Displays" })).toHaveAttribute("href", "/displays");
  });

  it("does not repeat the name as the description when the output is called the same", async () => {
    setup([{ ...KITCHEN, name: "Vestaboard" }]);
    params.boardId = "kitchen";
    renderWith(
      <DisplaysSection>
        <DisplayPage />
      </DisplaysSection>,
    );
    await screen.findByRole("heading", { level: 2, name: "Vestaboard" });
    const subheader = within(document.querySelector<HTMLElement>("[data-slot=page-subheader]")!);
    // Crumb + h2 only; no third "Vestaboard" underneath.
    expect(subheader.getAllByText("Vestaboard")).toHaveLength(2);
  });

  it("drops the old back button — the breadcrumb is the way back", async () => {
    setup([KITCHEN]);
    params.boardId = "kitchen";
    renderWith(
      <DisplaysSection>
        <DisplayPage />
      </DisplaysSection>,
    );
    await screen.findByRole("heading", { level: 2, name: "Kitchen" });
    expect(screen.queryByRole("link", { name: "All displays" })).not.toBeInTheDocument();
  });

  it("tucks Add a display away while a display is open", async () => {
    setup([KITCHEN]);
    params.boardId = "kitchen";
    renderWith(
      <DisplaysSection>
        <DisplayPage />
      </DisplaysSection>,
    );
    await screen.findByRole("heading", { level: 2, name: "Kitchen" });
    expect(screen.getByRole("button", { name: "Add a display" }).closest("[inert]")).not.toBeNull();
  });
});

describe("/displays/:boardId", () => {
  it("separates overview, settings and playback without losing the route board", async () => {
    setup([KITCHEN, DESK]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    expect(await screen.findByRole("tab", { name: "Overview", selected: true })).toBeInTheDocument();
    expect(screen.getByTestId("board-card")).not.toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Settings" }));
    expect(await screen.findByTestId("board-name-input")).toHaveValue("Desk Pixoo");
    await userEvent.click(screen.getByRole("tab", { name: "Playback" }));
    expect(await screen.findByTestId("display-transition")).toBeInTheDocument();
    expect(await screen.findByRole("switch", { name: "Silence Schedule" })).toBeInTheDocument();
    // Base UI finishes hiding the previous kept-mounted panel after the tab switch.
    await waitFor(() => expect(screen.getByTestId("board-card")).not.toBeVisible());
  });

  it("confirms display removal and lets Cancel leave it unchanged", async () => {
    const calls = setup([KITCHEN, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    await userEvent.click(await screen.findByRole("button", { name: "Remove Board" }));
    const confirmation = await screen.findByRole("alertdialog", { name: "Remove Kitchen?" });
    expect(calls.removed).toHaveLength(0);
    await userEvent.click(within(confirmation).getByRole("button", { name: "Cancel" }));
    expect(calls.removed).toHaveLength(0);
    expect(push).not.toHaveBeenCalled();
  });

  it("removes only the route display after confirmation", async () => {
    const calls = setup([KITCHEN, DESK]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    await userEvent.click(await screen.findByRole("button", { name: "Remove Board" }));
    const confirmation = await screen.findByRole("alertdialog", { name: "Remove Desk Pixoo?" });
    expect(calls.removed).toHaveLength(0);
    await userEvent.click(within(confirmation).getByRole("button", { name: "Remove Board" }));
    await waitFor(() => expect(calls.removed).toEqual(["desk"]));
    expect(push).toHaveBeenCalledWith("/displays");
  });

  it("groups playback controls in a named region for the route display", async () => {
    setup([KITCHEN, DESK]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const playback = await screen.findByRole("region", { name: "Playback" });
    expect(await within(playback).findByRole("switch", { name: "Silence Schedule" })).toBeInTheDocument();
    expect(within(playback).getByTestId("display-transition")).toBeInTheDocument();
  });

  it("shows that display's settings, preview and transition", async () => {
    setup([KITCHEN, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    const card = await screen.findByTestId("board-card");
    expect(within(card).getByTestId("board-name-input")).toHaveValue("Kitchen");
    await userEvent.click(screen.getByRole("tab", { name: "Playback" }));
    expect(screen.getByTestId("display-transition")).toBeInTheDocument();
    expect(screen.queryByTestId("display-panel-settings")).not.toBeInTheDocument();
  });

  it("says so for a display that no longer exists", async () => {
    setup([KITCHEN]);
    params.boardId = "gone";
    renderWith(<DisplayPage />);
    expect(await screen.findByTestId("display-not-found")).toBeInTheDocument();
  });

  // BB-A-20: an unknown id is named as not found (never shown as the title),
  // with the ways forward.
  it("titles an unknown display 'Display not found' and offers Back and Add", async () => {
    setup([KITCHEN]);
    params.boardId = "does-not-exist";
    renderWith(
      <DisplaysSection>
        <DisplayPage />
      </DisplaysSection>,
    );
    const notFound = await screen.findByTestId("display-not-found");
    expect(screen.getByRole("heading", { name: "Display not found" })).toBeInTheDocument();
    expect(screen.queryByText("does-not-exist")).not.toBeInTheDocument();
    expect(within(notFound).getByText("This display doesn’t exist anymore.")).toBeInTheDocument();
    expect(within(notFound).getByRole("link", { name: "Back to Displays" })).toHaveAttribute("href", "/displays");
    await userEvent.click(within(notFound).getByRole("button", { name: /Add a display/ }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("a split-flap selector offers None and the strategies its output animates", async () => {
    setup([KITCHEN]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const section = await screen.findByTestId("display-transition");
    const selector = within(section).getByRole("combobox", { name: "Transition" });
    expect(selector).toHaveTextContent("None");
    await userEvent.click(selector);
    expect(await screen.findByRole("option", { name: "Diagonal" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Default/ })).not.toBeInTheDocument();
    expect(within(section).queryByTestId("display-transition-cloud")).not.toBeInTheDocument();
  });

  it("saves the display's own transition with the board", async () => {
    const calls = setup([KITCHEN, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const section = await screen.findByTestId("display-transition");
    await userEvent.click(within(section).getByRole("combobox", { name: "Transition" }));
    await userEvent.click(await screen.findByRole("option", { name: "Diagonal" }));
    await waitFor(() => expect(calls.put).toHaveLength(1));
    const boards = calls.put[0].boards;
    expect(boards.find((b) => b.id === "kitchen")?.transition).toBe("diagonal");
    // Only that display's choice changes.
    expect(boards.find((b) => b.id === "desk")?.transition).toBeUndefined();
  });

  it("None is saved as the display's choice", async () => {
    const calls = setup([{ ...KITCHEN, transition: "row" }]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const section = await screen.findByTestId("display-transition");
    await userEvent.click(within(section).getByRole("combobox", { name: "Transition" }));
    await userEvent.click(await screen.findByRole("option", { name: "None" }));
    await waitFor(() => expect(calls.put).toHaveLength(1));
    expect(calls.put[0].boards[0].transition).toBe("none");
  });

  it("a native strategy shows its speed, and a step interval saves with the display", async () => {
    const calls = setup([{ ...KITCHEN, transition: "row", transition_step_size: 2 }, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const interval = await screen.findByRole("spinbutton", { name: "Step Interval (ms)" });
    expect(screen.getByRole("spinbutton", { name: "Step Size" })).toHaveValue(2);
    await userEvent.type(interval, "40");
    await userEvent.tab();
    await waitFor(() => expect(calls.put).toHaveLength(1));
    const boards = calls.put[0].boards;
    expect(boards.find((b) => b.id === "kitchen")).toMatchObject({
      transition: "row",
      transition_step_interval_ms: 40,
      transition_step_size: 2,
    });
    expect(boards.find((b) => b.id === "desk")?.transition_step_interval_ms).toBeUndefined();
  });

  it("clearing a speed field saves the device's default", async () => {
    const calls = setup([{ ...KITCHEN, transition: "row", transition_step_size: 3 }]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const size = await screen.findByRole("spinbutton", { name: "Step Size" });
    await userEvent.clear(size);
    await userEvent.tab();
    await waitFor(() => expect(calls.put).toHaveLength(1));
    expect(calls.put[0].boards[0].transition_step_size).toBeNull();
  });

  it("a step size below 1 is not saved", async () => {
    const calls = setup([{ ...KITCHEN, transition: "row" }]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const size = await screen.findByRole("spinbutton", { name: "Step Size" });
    await userEvent.type(size, "0");
    await userEvent.tab();
    expect(size).toHaveAttribute("aria-invalid", "true");
    expect(calls.put).toHaveLength(0);
  });

  it("a step interval above 5000 ms is not saved", async () => {
    const calls = setup([{ ...KITCHEN, transition: "row" }]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const interval = await screen.findByRole("spinbutton", { name: "Step Interval (ms)" });
    expect(interval).toHaveAttribute("max", "5000");
    await userEvent.type(interval, "5001");
    await userEvent.tab();
    expect(interval).toHaveAttribute("aria-invalid", "true");
    expect(calls.put).toHaveLength(0);
  });

  it("None has no speed to set", async () => {
    setup([{ ...KITCHEN, transition: "none" }]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    await screen.findByTestId("display-transition");
    expect(screen.getByRole("combobox", { name: "Transition" })).toHaveTextContent("None");
    expect(screen.queryByTestId("display-transition-speed")).not.toBeInTheDocument();
  });

  it("turns transition plugins on for every display from a split-flap display", async () => {
    let body: unknown = null;
    setup([KITCHEN]);
    server.use(
      http.put(`${API}/settings/plugins`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          auto_update: true,
          transition_plugins_enabled: true,
        });
      }),
    );
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const section = await screen.findByTestId("display-transition-plugins");
    expect(section).toHaveTextContent(/all displays/i);
    const toggle = within(section).getByRole("switch", { name: "Transition Plugins" });
    expect(toggle).not.toBeChecked();
    await userEvent.click(toggle);
    await waitFor(() => expect(body).toEqual({ transition_plugins_enabled: true }));
  });

  it("offers no transition plugins switch where frames cannot run", async () => {
    setup([{ ...KITCHEN, output_config: { api_mode: "cloud", cloud_key: "***" } }, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    await screen.findByTestId("display-transition-cloud");
    expect(screen.queryByTestId("display-transition-plugins")).not.toBeInTheDocument();
  });

  it("a cloud Vestaboard says it changes all at once", async () => {
    setup([{ ...KITCHEN, output_config: { api_mode: "cloud", cloud_key: "***" } }]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    expect(await screen.findByTestId("display-transition-cloud")).toBeInTheDocument();
  });

  it("a Pixoo offers every LED transition at 5 frames a second, without the snap note", async () => {
    setup([KITCHEN, DESK]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const section = await screen.findByTestId("display-transition");
    expect(within(section).queryByTestId("display-transition-snaps")).not.toBeInTheDocument();
    const selector = within(section).getByRole("combobox", { name: "Transition" });
    expect(selector).toHaveTextContent("Device default");
    await userEvent.click(selector);
    expect(screen.queryByRole("option", { name: /Diagonal/ })).not.toBeInTheDocument();
    await screen.findByRole("option", { name: "Flip" });
    const offered = [
      "Device default",
      "None — change instantly",
      "Flip",
      "Cascade",
      "Slide",
      "Wipe",
      "Fade",
      "Dissolve",
    ];
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(offered);
    expect(screen.getAllByRole("option").every((option) => !option.hasAttribute("aria-disabled"))).toBe(true);
  });

  it("an LED display that only snaps says so", async () => {
    setup([KITCHEN, { ...DESK, device_model: "ulanzi_tc001_awtrix" }]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const section = await screen.findByTestId("display-transition");
    expect(within(section).getByTestId("display-transition-snaps")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("combobox", { name: "Transition" }));
    expect(await screen.findByRole("option", { name: /None/ })).toBeInTheDocument();
  });

  it("a faster LED display offers the transitions it can run, without the snap note", async () => {
    setup([KITCHEN, { ...DESK, device_model: "hub75_64x32" }]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const section = await screen.findByTestId("display-transition");
    expect(within(section).queryByTestId("display-transition-snaps")).not.toBeInTheDocument();
    await userEvent.click(within(section).getByRole("combobox", { name: "Transition" }));
    expect(await screen.findByRole("option", { name: "Flip" })).toBeInTheDocument();
  });

  it("keeps the panel's display name in its inline card and advanced board controls collapsed", async () => {
    const calls = setup([KITCHEN, TV]);
    params.boardId = "tv";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    const panel = await screen.findByTestId("display-panel-settings");
    const name = await within(panel).findByTestId("board-name-input");
    expect(name).toHaveValue("Living Room (Panel)");
    expect(screen.queryByRole("button", { name: "Remove Board" })).not.toBeInTheDocument();
    await userEvent.clear(name);
    await userEvent.type(name, "TV only");
    await userEvent.tab();
    await waitFor(() => expect(calls.put).toHaveLength(1));
    expect(calls.put[0].boards.find((item) => item.id === "tv")?.name).toBe("TV only");
    expect(calls.put[0].boards.find((item) => item.id === "kitchen")?.name).toBe("Kitchen");
    await userEvent.click(within(panel).getByRole("button", { name: "Advanced display settings" }));
    expect(await within(panel).findByTestId("board-pause-switch")).toBeVisible();
    expect(within(panel).getAllByTestId("board-name-input")).toHaveLength(1);
  });

  it("a FiestaPanel's page carries its panel's controls, and only its panel", async () => {
    setup([KITCHEN, TV]);
    params.boardId = "tv";
    renderWith(<DisplayPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    const panel = await screen.findByTestId("display-panel-settings");
    expect(((await within(panel).findByLabelText("Panel URL")) as HTMLInputElement).value).toContain("/p/1");
    expect(within(panel).queryByDisplayValue("Bedroom")).not.toBeInTheDocument();
    // New panels come from Add a display, not from a panel's page.
    expect(within(panel).queryByRole("button", { name: "Create panel" })).not.toBeInTheDocument();
  });
});

// 07d `320:17086` / `328:27519` on a phone (BB-A-19, BB-A-24): no card around
// the section, no section description; the list is "Displays" with Add display
// beside it; a display is "‹ Displays", its name, then the tabs — one way back.
describe("Displays on a phone", () => {
  function asPhone() {
    const media = originalMatchMedia("");
    window.matchMedia = vi.fn((query) => ({
      ...media,
      media: query,
      matches: query.includes("max-width: 1023.98px") || query.includes("max-width: 767.98px"),
    }));
  }

  it("draws the list without a card or description, causes whole", async () => {
    asPhone();
    setup([KITCHEN, TV]);
    server.use(http.get(`${API}/auth/sessions`, () => HttpResponse.json({ sessions: [], total: 0 })));
    const { container } = renderWith(
      <DisplaysSection>
        <DisplaysPage />
      </DisplaysSection>,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Displays" })).toBeInTheDocument();
    expect(container.querySelector('[data-slot="page-card"]')).toHaveAttribute("data-surface", "plain");
    expect(screen.queryByText(/Every board and screen FiestaBoard shows on/)).not.toBeInTheDocument();
    expect(screen.getByTestId("add-display")).toBeInTheDocument();
    // 07d: the status word is tinted, in the kit's text tone (AA on the page).
    expect(await screen.findByText("No viewer")).toHaveClass("text-hue-yellow");
    // The mobile frame has no Your displays / Marketplace tabs; Add display
    // reaches the outputs.
    expect(screen.queryByRole("tab", { name: /Marketplace/ })).not.toBeInTheDocument();
    // No card inset or hairline around the outlet.
    expect(container.querySelector('[data-slot="page-outlet"]')).toHaveAttribute("data-surface", "plain");
    const cause = await screen.findByText("No signed-in TV is showing this display");
    expect(cause.className).not.toMatch(/\btruncate\b/);
  });

  it("opens a display with one way back, its name, then the tabs", async () => {
    asPhone();
    setup([KITCHEN]);
    params.boardId = "kitchen";
    renderWith(
      <DisplaysSection>
        <DisplayPage />
      </DisplaysSection>,
    );
    const back = await screen.findByRole("link", { name: "Displays" });
    expect(back).toHaveAttribute("href", "/displays");
    expect(await screen.findByRole("heading", { level: 1, name: "Kitchen" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /breadcrumb/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Back to Displays" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Now showing" })).not.toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: "Overview" })).toBeInTheDocument();
  });

  // Review (#2568): the phone inset override must not reach sections that are
  // a card's content (Playback, Diagnostics), only the page's own sections.
  it("keeps the inset of sections inside cards on the Playback tab", async () => {
    asPhone();
    setup([KITCHEN]);
    params.boardId = "kitchen";
    const { container } = renderWith(
      <DisplaysSection>
        <DisplayPage />
      </DisplaysSection>,
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Playback" }));
    const wrapper = container.querySelector('[data-slot="page-card"][data-surface="plain"]')!;
    const rule = wrapper.className.split(/\s+/).find((c) => c.includes("data-slot=page-section"));
    expect(rule).toBe("[&_[data-slot=page-section]:not([data-slot=card]_*)]:px-0");
    const inCard = wrapper.querySelector('[data-slot="card"] [data-slot="page-section"]');
    expect(inCard).not.toBeNull();
    expect(inCard!.matches('[data-slot="page-section"]:not([data-slot="card"] *)')).toBe(false);
  });

  it("moves focus to the display's name when drilling in, not to the page body", async () => {
    asPhone();
    setup([KITCHEN]);
    const { rerender } = renderWith(
      <DisplaysSection>
        <DisplaysPage />
      </DisplaysSection>,
    );
    await screen.findByRole("heading", { level: 1, name: "Displays" });
    params.boardId = "kitchen";
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <DisplaysSection>
          <DisplayPage />
        </DisplaysSection>
      </QueryClientProvider>,
    );
    const heading = await screen.findByRole("heading", { level: 1, name: "Kitchen" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });
});

// Review (#2568, round 5): crossing the phone breakpoint must not remount the
// page (a rotated tablet lost the list's selection).
describe("Displays across the phone breakpoint", () => {
  it("keeps the same outlet element when the layout switches", async () => {
    let phone = false;
    const listeners: EventListener[] = [];
    window.matchMedia = vi.fn(
      (query: string) =>
        ({
          media: query,
          get matches() {
            return query.includes("max-width: 767.98px") ? phone : query.includes("max-width: 1023.98px");
          },
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: (_type: string, listener: EventListener) => listeners.push(listener),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList,
    );
    setup([KITCHEN]);
    const { container } = renderWith(
      <DisplaysSection>
        <DisplaysPage />
      </DisplaysSection>,
    );
    await screen.findByTestId("display-card");
    const outlet = container.querySelector('[data-slot="page-outlet"]');
    phone = true;
    act(() => listeners.forEach((listener) => listener(new Event("change"))));
    await screen.findByRole("heading", { level: 1, name: "Displays" });
    expect(container.querySelector('[data-slot="page-outlet"]')).toBe(outlet);
  });
});
