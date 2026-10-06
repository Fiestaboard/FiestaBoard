/**
 * Displays (plan D21): the list (/displays) and one display's page
 * (/displays/:boardId) — live preview, output, state, quick actions,
 * the settings screen, the transition from the device's menu, and a
 * FiestaPanel's own controls.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DisplaysSection } from "../../app/routes/displays";
import DisplaysPage from "../../app/routes/displays._index";
import DisplayPage from "../../app/routes/displays.$boardId";
import { mockOutputs, mockStatus } from "./mocks/handlers";
import { server } from "./mocks/server";

const push = vi.fn();
const params: { boardId?: string } = {};

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
  const calls = { put: [] as { boards: Record<string, unknown>[] }[], pause: [] as unknown[] };
  let stored = boards;
  server.use(
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards: stored, devices: [] })),
    http.put(`${API}/settings/board`, async ({ request }) => {
      const body = (await request.json()) as { boards: Record<string, unknown>[] };
      calls.put.push(body);
      stored = body.boards;
      return HttpResponse.json({ board_type: "black", boards: stored, devices: [] });
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

describe("/displays", () => {
  it("lists every display with its name, output and a way into its settings", async () => {
    setup([KITCHEN, DESK]);
    renderWith(<DisplaysPage />);
    const cards = await screen.findAllByTestId("display-card");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText("Kitchen")).toBeInTheDocument();
    await waitFor(() => expect(within(cards[0]).getByTestId("display-output")).toHaveTextContent("Vestaboard"));
    expect(within(cards[1]).getByTestId("display-output")).toHaveTextContent("Divoom Pixoo");
    expect(within(cards[1]).getByRole("link", { name: "Open settings for Desk Pixoo" })).toHaveAttribute(
      "href",
      "/displays/desk",
    );
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
    expect(await within(cards[0]).findByTestId("board-status-badge")).toHaveTextContent("Connected");
    expect(await within(cards[1]).findByTestId("board-status-badge")).toHaveTextContent("Not configured");
  });

  it("draws an LED display as its LED matrix and a split-flap one as flaps", async () => {
    setup([KITCHEN, DESK]);
    renderWith(<DisplaysPage />);
    const cards = await screen.findAllByTestId("display-card");
    await waitFor(() =>
      expect(cards[1].querySelector("[data-slot='display-preview']")).toHaveAttribute("data-model", "divoom_pixoo64"),
    );
    expect(cards[0].querySelector("[data-slot='display-preview']")).toBeNull();
  });

  it("pauses a display from its card", async () => {
    const calls = setup([KITCHEN]);
    renderWith(<DisplaysPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Pause Kitchen" }));
    await waitFor(() => expect(calls.pause).toEqual([{ board: "kitchen", paused: true }]));
  });

  it("offers Resume on a paused display", async () => {
    setup([{ ...KITCHEN, paused: true }]);
    renderWith(<DisplaysPage />);
    expect(await screen.findByRole("button", { name: "Resume Kitchen" })).toBeInTheDocument();
    expect(screen.getByTestId("board-paused-badge")).toBeInTheDocument();
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
    renderWith(
      <DisplaysSection>
        <DisplaysPage />
      </DisplaysSection>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Add a display" }));
    await userEvent.click(await screen.findByRole("radio", { name: /Vestaboard/ }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Note" }));
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
  it("shows that display's settings, preview and transition", async () => {
    setup([KITCHEN, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    const card = await screen.findByTestId("board-card");
    expect(within(card).getByTestId("board-name-input")).toHaveValue("Kitchen");
    expect(screen.getByTestId("display-transition")).toBeInTheDocument();
    expect(screen.queryByTestId("display-panel-settings")).not.toBeInTheDocument();
  });

  it("says so for a display that no longer exists", async () => {
    setup([KITCHEN]);
    params.boardId = "gone";
    renderWith(<DisplayPage />);
    expect(await screen.findByTestId("display-not-found")).toBeInTheDocument();
  });

  it("a split-flap display offers None and the strategies its output animates, and no Default", async () => {
    setup([KITCHEN]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    const section = await screen.findByTestId("display-transition");
    const group = within(section).getByRole("radiogroup", { name: "Transition" });
    await waitFor(() => expect(within(group).getByRole("radio", { name: /Diagonal/ })).toBeInTheDocument());
    // Settings v6: every display owns its transition; there is no install default to follow.
    expect(within(group).queryByRole("radio", { name: /Default/ })).not.toBeInTheDocument();
    // An unset choice runs as no transition, and reads as None.
    expect(within(group).getByRole("radio", { name: /None/ })).toHaveAttribute("aria-checked", "true");
    expect(within(section).queryByTestId("display-transition-cloud")).not.toBeInTheDocument();
  });

  it("saves the display's own transition with the board", async () => {
    const calls = setup([KITCHEN, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    const section = await screen.findByTestId("display-transition");
    await userEvent.click(await within(section).findByRole("radio", { name: /Diagonal/ }));
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
    const section = await screen.findByTestId("display-transition");
    await userEvent.click(within(section).getByRole("radio", { name: /None/ }));
    await waitFor(() => expect(calls.put).toHaveLength(1));
    expect(calls.put[0].boards[0].transition).toBe("none");
  });

  it("a native strategy shows its speed, and a step interval saves with the display", async () => {
    const calls = setup([{ ...KITCHEN, transition: "row", transition_step_size: 2 }, DESK]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
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
    await screen.findByTestId("display-transition");
    await waitFor(() => expect(screen.getByRole("radio", { name: /Diagonal/ })).toBeInTheDocument());
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
    await screen.findByTestId("display-transition-cloud");
    expect(screen.queryByTestId("display-transition-plugins")).not.toBeInTheDocument();
  });

  it("a cloud Vestaboard says it changes all at once", async () => {
    setup([{ ...KITCHEN, output_config: { api_mode: "cloud", cloud_key: "***" } }]);
    params.boardId = "kitchen";
    renderWith(<DisplayPage />);
    expect(await screen.findByTestId("display-transition-cloud")).toBeInTheDocument();
  });

  it("a Pixoo shows the LED menu and says it snaps", async () => {
    setup([KITCHEN, DESK]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    const section = await screen.findByTestId("display-transition");
    expect(within(section).getByTestId("display-transition-snaps")).toBeInTheDocument();
    // No split-flap strategies on an LED display.
    expect(within(section).queryByRole("radio", { name: /Diagonal/ })).not.toBeInTheDocument();
    expect(within(section).getByRole("radio", { name: /None/ })).toBeInTheDocument();
  });

  it("a faster LED display offers the transitions it can run, without the snap note", async () => {
    setup([KITCHEN, { ...DESK, device_model: "hub75_64x32" }]);
    params.boardId = "desk";
    renderWith(<DisplayPage />);
    const section = await screen.findByTestId("display-transition");
    expect(within(section).queryByTestId("display-transition-snaps")).not.toBeInTheDocument();
    expect(within(section).getByRole("radio", { name: /Flip/ })).toBeInTheDocument();
  });

  it("a FiestaPanel's page carries its panel's controls, and only its panel", async () => {
    setup([KITCHEN, TV]);
    params.boardId = "tv";
    renderWith(<DisplayPage />);
    const panel = await screen.findByTestId("display-panel-settings");
    expect(await within(panel).findByText("Living Room")).toBeInTheDocument();
    expect(within(panel).queryByText("Bedroom")).not.toBeInTheDocument();
    // New panels come from Add a display, not from a panel's page.
    expect(within(panel).queryByRole("button", { name: "Create panel" })).not.toBeInTheDocument();
  });
});
