/**
 * The board settings screen rendered from an output's declaration (plan D13):
 * sections, `ui:visible_when`, the core widgets (mode-cards, device-picker,
 * tile-grid), action buttons with input dialogs, and result rendering —
 * against the draft route before a board exists and the saved-board route
 * after.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { tileActionInput } from "@/components/plugin-settings/board-widgets";
import { PluginBoardSettings } from "@/components/settings/plugin-board-settings";
import type { ActionResult, OutputSummary } from "@/lib/api";

import { server } from "./mocks/server";

const API = "/api";

const OUTPUT: OutputSummary = {
  id: "acme_sign",
  name: "Acme Sign",
  description: "A test sign.",
  icon: "monitor",
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
  device_models: [{ id: "divoom_pixoo64", label: "Divoom Pixoo 64" }],
  settings_schema: {
    type: "object",
    properties: {
      mode: {
        type: "string",
        title: "Connection",
        enum: ["lan", "cloud"],
        default: "lan",
        "ui:widget": "mode-cards",
        "ui:options": {
          cards: [
            { value: "lan", title: "On my network", description: "Talk to the sign directly." },
            { value: "cloud", title: "Cloud", description: "Through Acme's servers." },
          ],
        },
      },
      host: { type: "string", title: "Sign address", "ui:widget": "device-picker", "ui:visible_when": { mode: "lan" } },
      cloud_key: { type: "string", title: "Cloud key", secret: true, "ui:visible_when": { mode: "cloud" } },
      token: { type: "string", title: "Pairing token", secret: true },
      brightness: { type: "integer", title: "Brightness" },
    },
    "ui:sections": [
      { id: "connection", title: "Connection settings", fields: ["mode", "host", "cloud_key", "token"] },
      { id: "advanced", title: "Advanced", fields: ["brightness"], collapsible: true, collapsed: true },
    ],
  },
  actions: [
    {
      id: "test_connection",
      label: "Test connection",
      description: "",
      builtin: true,
      input_schema: null,
      result_fields: {},
    },
    { id: "discover", label: "Find signs", description: "", builtin: true, input_schema: null, result_fields: {} },
    {
      id: "detect_geometry",
      label: "Detect size",
      description: "",
      builtin: true,
      input_schema: null,
      result_fields: {},
    },
    {
      id: "pair",
      label: "Pair",
      description: "Pair using the code on the sign.",
      builtin: false,
      input_schema: {
        type: "object",
        properties: { code: { type: "string", title: "Pairing code" } },
        required: ["code"],
      },
      result_fields: { token: { secret: true, fills: "token" } },
    },
  ],
};

function result(overrides: Partial<ActionResult> = {}): ActionResult {
  return { status: "ok", message: "", guidance: [], fields: null, geometry: null, devices: null, ...overrides };
}

function Harness(props: { boardId?: string; initial?: Record<string, unknown>; onGeometry?: () => void }) {
  const [values, setValues] = useState<Record<string, unknown>>(props.initial ?? {});
  return (
    <>
      <PluginBoardSettings
        output={OUTPUT}
        values={values}
        onChange={setValues}
        boardId={props.boardId}
        deviceModel="divoom_pixoo64"
        onGeometry={props.onGeometry}
      />
      <output data-testid="values">{JSON.stringify(values)}</output>
    </>
  );
}

function renderScreen(props: Parameters<typeof Harness>[0] = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness {...props} />
    </QueryClientProvider>,
  );
}

function values(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId("values").textContent ?? "{}");
}

describe("PluginBoardSettings — the schema", () => {
  it("groups fields into sections, the collapsed one closed", async () => {
    renderScreen();
    const connection = screen.getByTestId("schema-section-connection");
    expect(within(connection).getByText("Connection settings")).toBeInTheDocument();
    expect(screen.queryByLabelText("Brightness")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Advanced" }));
    expect(await screen.findByLabelText("Brightness")).toBeInTheDocument();
  });

  it("shows a field only while ui:visible_when holds", async () => {
    renderScreen();
    expect(screen.getByLabelText("Sign address")).toBeInTheDocument();
    expect(screen.queryByLabelText("Cloud key")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Cloud/ }));
    expect(values().mode).toBe("cloud");
    expect(screen.queryByLabelText("Sign address")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Cloud key")).toBeInTheDocument();
  });

  it("renders mode-cards as a labelled radiogroup", () => {
    renderScreen();
    const group = screen.getByRole("radiogroup", { name: "Connection" });
    expect(within(group).getByRole("radio", { name: /On my network/ })).toHaveAttribute("aria-checked", "true");
  });

  it("renders a secret field as a secret input", () => {
    renderScreen();
    expect(screen.getByLabelText("Pairing token")).toHaveAttribute("type", "password");
  });
});

describe("PluginBoardSettings — actions", () => {
  it("runs an action on the draft route with the settings being typed", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API}/outputs/acme_sign/actions/test_connection`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          result({ status: "error", message: "Sign refused the token.", guidance: ["Pair again."] }),
        );
      }),
    );
    renderScreen({ initial: { host: "192.0.2.5" } });
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));

    const panel = await screen.findByTestId("action-result");
    expect(panel).toHaveAttribute("data-status", "error");
    expect(within(panel).getByText("Sign refused the token.")).toBeInTheDocument();
    expect(within(panel).getByText("Pair again.")).toBeInTheDocument();
    expect(body).toEqual({ output_config: { host: "192.0.2.5" }, device_model: "divoom_pixoo64" });
  });

  it("runs a saved board's action on the board route", async () => {
    let called = false;
    server.use(
      http.post(`${API}/boards/b1/actions/test_connection`, async ({ request }) => {
        called = true;
        expect(await request.json()).toEqual({ output_config: { token: "***" } });
        return HttpResponse.json(result({ message: "Reachable." }));
      }),
    );
    renderScreen({ boardId: "b1", initial: { token: "***" } });
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("Reachable.")).toBeInTheDocument();
    expect(called).toBe(true);
  });

  it("asks for an action's input, then fills a secret result into its field", async () => {
    let input: unknown = null;
    server.use(
      http.post(`${API}/outputs/acme_sign/actions/pair`, async ({ request }) => {
        input = ((await request.json()) as { input: unknown }).input;
        return HttpResponse.json(
          result({
            message: "Paired.",
            fields: { token: { value: "test_paired_token", secret: true, fills: "token" } },
          }),
        );
      }),
    );
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Pair" }));
    const dialog = await screen.findByRole("dialog");
    const next = within(dialog).getByRole("button", { name: "Next" });
    expect(next).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Pairing code/), "1234");
    await userEvent.click(next);

    expect(await screen.findByText("Paired.")).toBeInTheDocument();
    expect(input).toEqual({ code: "1234" });
    expect(values().token).toBe("test_paired_token");
    const token = screen.getByLabelText("Pairing token");
    expect(token).toHaveAttribute("type", "password");
    expect(token).toHaveValue("test_paired_token");
    expect(screen.getByText("Filled in: Pairing token")).toBeInTheDocument();
  });

  it("submitting an action's input dialog never submits a form around the screen", async () => {
    // The dialog renders in a portal, but React bubbles its submit through
    // the component tree: a host screen that is itself a <form> (the Add
    // Board dialog) would otherwise be submitted too.
    server.use(
      http.post(`${API}/outputs/acme_sign/actions/pair`, () => HttpResponse.json(result({ message: "Paired." }))),
    );
    const outerSubmit = vi.fn((event: { preventDefault: () => void }) => event.preventDefault());
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <form onSubmit={outerSubmit}>
          <Harness />
        </form>
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Pair" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Pairing code/), "1234{Enter}");

    expect(await screen.findByText("Paired.")).toBeInTheDocument();
    expect(outerSubmit).not.toHaveBeenCalled();
  });

  it("offers a detected size to apply", async () => {
    const onGeometry = vi.fn();
    const geometry = {
      device_type: "panel" as const,
      rows: 10,
      cols: 16,
      notes_wide: null,
      notes_tall: null,
      matched_preset: null,
    };
    server.use(
      http.post(`${API}/outputs/acme_sign/actions/detect_geometry`, () => HttpResponse.json(result({ geometry }))),
    );
    renderScreen({ onGeometry });
    await userEvent.click(screen.getByRole("button", { name: "Detect size" }));
    expect(await screen.findByText("Detected 10 × 16")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply size" }));
    expect(onGeometry).toHaveBeenCalledWith(geometry);
  });

  it("shows a refused action's detail", async () => {
    server.use(
      http.post(`${API}/outputs/acme_sign/actions/test_connection`, () =>
        HttpResponse.json({ detail: "A draft has no stored secret to restore: enter token" }, { status: 400 }),
      ),
    );
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByTestId("action-failure")).toHaveTextContent("A draft has no stored secret");
  });

  it("finds devices from the device picker instead of a separate button", async () => {
    server.use(
      http.post(`${API}/outputs/acme_sign/actions/discover`, () =>
        HttpResponse.json(
          result({ devices: [{ ip: "192.0.2.77", port: 80, hostname: "acme.local", source: "mdns", label: null }] }),
        ),
      ),
    );
    renderScreen();
    expect(screen.queryByRole("button", { name: "Find signs" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Find devices" }));
    await userEvent.click(await screen.findByRole("radio", { name: /acme\.local/ }));
    await waitFor(() => expect(values().host).toBe("192.0.2.77"));
  });
});

describe("tile-grid", () => {
  const TILE_OUTPUT: OutputSummary = {
    ...OUTPUT,
    settings_schema: {
      type: "object",
      properties: {
        wide: { type: "integer", title: "Notes wide" },
        tall: { type: "integer", title: "Notes tall" },
        tiles: {
          type: "array",
          title: "Tiles",
          "ui:widget": "tile-grid",
          "ui:options": { rows_field: "tall", cols_field: "wide" },
          items: {
            type: "object",
            properties: {
              row: { type: "integer" },
              col: { type: "integer" },
              host: { type: "string", title: "Tile address" },
            },
          },
        },
      },
    },
    actions: [],
  };

  function TileHarness() {
    const [v, setV] = useState<Record<string, unknown>>({ wide: 2, tall: 1, tiles: [] });
    return (
      <>
        <PluginBoardSettings output={TILE_OUTPUT} values={v} onChange={setV} />
        <output data-testid="values">{JSON.stringify(v)}</output>
      </>
    );
  }

  it("assigns a tile through its slot's dialog", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <TileHarness />
      </QueryClientProvider>,
    );
    const grid = screen.getByRole("group", { name: "Tiles" });
    expect(within(grid).getAllByRole("button")).toHaveLength(2);
    await userEvent.click(within(grid).getByRole("button", { name: /Tile 2: row 1, column 2/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Tile address"), "192.0.2.8");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save tile" }));
    await waitFor(() => expect(values().tiles).toEqual([{ row: 0, col: 1, host: "192.0.2.8" }]));
  });

  it("acts on a saved tile by position alone, never with a masked key", () => {
    const identify = {
      id: "identify",
      label: "Identify",
      description: "",
      builtin: true,
      input_schema: { type: "object", properties: { target: {}, row: {}, col: {}, host: {}, local_api_key: {} } },
      result_fields: {},
    };
    expect(tileActionInput(identify, { row: 0, col: 1, host: "192.0.2.8", local_api_key: "***" })).toEqual({
      row: 0,
      col: 1,
    });
    expect(tileActionInput(identify, { row: 0, col: 1, host: "192.0.2.8", local_api_key: "k", enabled: true })).toEqual(
      { row: 0, col: 1, host: "192.0.2.8", local_api_key: "k" },
    );
  });
});

describe("the contract's board facts, conditional actions and auto-apply", () => {
  const SHAPED: OutputSummary = {
    ...OUTPUT,
    id: "shaped_sign",
    settings_schema: {
      type: "object",
      properties: {
        mode: { type: "string", title: "Mode", enum: ["lan", "cloud"], default: "lan", "ui:widget": "mode-cards" },
        host: {
          type: "string",
          title: "Sign address",
          "ui:visible_when": { mode: "lan", "@device_type": ["flagship", "note"] },
        },
        array_token: {
          type: "string",
          title: "Array token",
          secret: true,
          "ui:visible_when": { "@device_type": "note_array" },
        },
        tiles: {
          type: "array",
          title: "Tiles",
          "ui:widget": "tile-grid",
          "ui:options": { layout: "board", item_actions: ["pair"] },
          "ui:visible_when": { mode: "lan", "@device_type": "note_array" },
          items: {
            type: "object",
            required: ["host"],
            properties: {
              row: { type: "integer" },
              col: { type: "integer" },
              host: { type: "string", title: "Tile address" },
            },
          },
        },
      },
      required: ["host", "array_token"],
    },
    actions: [
      {
        id: "test_connection",
        label: "Test connection",
        description: "",
        builtin: true,
        input_schema: null,
        result_fields: {},
      },
      {
        id: "detect_geometry",
        label: "Detect size",
        description: "",
        builtin: true,
        input_schema: null,
        result_fields: {},
        auto_apply: true,
        visible_when: { not: { mode: "lan", "@device_type": "note_array" } },
      },
      {
        id: "pair",
        label: "Pair",
        description: "",
        builtin: false,
        input_schema: {
          type: "object",
          properties: { code: { type: "string", title: "Pairing code" }, host: { type: "string", title: "Address" } },
          required: ["code"],
        },
        result_fields: {},
        visible_when: { mode: "lan" },
      },
    ],
  };

  function Shaped(props: {
    facts: { device_type: string };
    initial?: Record<string, unknown>;
    onGeometry?: (geometry: unknown) => void;
  }) {
    const [v, setV] = useState<Record<string, unknown>>(props.initial ?? {});
    return (
      <QueryClientProvider client={new QueryClient()}>
        <PluginBoardSettings
          output={SHAPED}
          values={v}
          onChange={setV}
          boardId="b1"
          facts={props.facts}
          layout={{ rows: 2, cols: 3 }}
          onGeometry={props.onGeometry}
        />
        <output data-testid="values">{JSON.stringify(v)}</output>
      </QueryClientProvider>
    );
  }

  it("shows each board shape only its own fields (@device_type)", () => {
    const { unmount } = render(<Shaped facts={{ device_type: "flagship" }} />);
    expect(screen.getByLabelText(/Sign address/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Array token/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("tile-grid-assignment")).not.toBeInTheDocument();
    unmount();
    render(<Shaped facts={{ device_type: "note_array" }} />);
    expect(screen.queryByLabelText(/Sign address/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Array token/)).toBeInTheDocument();
  });

  it("sizes a layout-board tile grid by the board's own layout", () => {
    render(<Shaped facts={{ device_type: "note_array" }} />);
    expect(within(screen.getByTestId("tile-grid")).getAllByRole("button")).toHaveLength(6);
    expect(screen.getByText("0/6 tiles assigned")).toBeInTheDocument();
  });

  it("names the visible required settings still empty, and only those", () => {
    render(<Shaped facts={{ device_type: "flagship" }} />);
    expect(screen.getByTestId("settings-missing")).toHaveTextContent("Still needed: Sign address");
  });

  it("shows an action only while its condition holds, and never one a visible widget runs", async () => {
    const { unmount } = render(<Shaped facts={{ device_type: "flagship" }} />);
    expect(screen.getByRole("button", { name: "Detect size" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pair" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "cloud" }));
    expect(screen.queryByRole("button", { name: "Pair" })).not.toBeInTheDocument();
    unmount();
    // A local array: no size to detect; Pair belongs to the tiles.
    render(<Shaped facts={{ device_type: "note_array" }} />);
    expect(screen.queryByRole("button", { name: "Detect size" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pair" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Test connection" })).toBeInTheDocument();
  });

  it("applies an auto_apply action's geometry at once", async () => {
    const onGeometry = vi.fn();
    const geometry = {
      device_type: "flagship" as const,
      rows: 6,
      cols: 22,
      notes_wide: null,
      notes_tall: null,
      matched_preset: null,
    };
    server.use(http.post(`${API}/boards/b1/actions/detect_geometry`, () => HttpResponse.json(result({ geometry }))));
    render(<Shaped facts={{ device_type: "flagship" }} onGeometry={onGeometry} />);
    await userEvent.click(screen.getByRole("button", { name: "Detect size" }));
    expect(await screen.findByText("Set to 6 × 22")).toBeInTheDocument();
    expect(onGeometry).toHaveBeenCalledWith(geometry);
    expect(screen.queryByRole("button", { name: "Apply size" })).not.toBeInTheDocument();
  });

  it("starts an action's input from the settings of the same name, never a masked one", async () => {
    let input: unknown = null;
    server.use(
      http.post(`${API}/boards/b1/actions/pair`, async ({ request }) => {
        input = ((await request.json()) as { input: unknown }).input;
        return HttpResponse.json(result({ message: "Paired." }));
      }),
    );
    render(<Shaped facts={{ device_type: "flagship" }} initial={{ host: "192.0.2.9", array_token: "***" }} />);
    await userEvent.click(screen.getByRole("button", { name: "Pair" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Address")).toHaveValue("192.0.2.9");
    await userEvent.type(within(dialog).getByLabelText(/Pairing code/), "42");
    await userEvent.click(within(dialog).getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Paired.")).toBeInTheDocument();
    expect(input).toEqual({ host: "192.0.2.9", code: "42" });
  });

  it("runs a tile action with the tile's own values and asks in the tile for the rest", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API}/boards/b1/actions/pair`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(result({ message: "Paired." }));
      }),
    );
    render(
      <Shaped facts={{ device_type: "note_array" }} initial={{ tiles: [{ row: 1, col: 2, host: "192.0.2.4" }] }} />,
    );
    await userEvent.click(screen.getByTestId("tile-slot-1-2"));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Pair" }));
    const asked = within(dialog).getByRole("group", { name: "Pair" });
    // Only what the tile cannot give is asked for.
    expect(within(asked).queryByLabelText("Address")).not.toBeInTheDocument();
    await userEvent.type(within(asked).getByLabelText(/Pairing code/), "77");
    await userEvent.click(within(asked).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body!.input).toEqual({ host: "192.0.2.4", code: "77" });
  });
});
