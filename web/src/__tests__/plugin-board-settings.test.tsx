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

import { identifyInput } from "@/components/plugin-settings/board-widgets";
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
    await userEvent.click(within(grid).getByRole("button", { name: "Row 1, column 2" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Tile address"), "192.0.2.8");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(values().tiles).toEqual([{ row: 0, col: 1, host: "192.0.2.8" }]));
  });

  it("identifies a saved tile by position alone, never with a masked key", () => {
    const identify = {
      id: "identify",
      label: "Identify",
      description: "",
      builtin: true,
      input_schema: { type: "object", properties: { target: {}, row: {}, col: {}, host: {}, local_api_key: {} } },
      result_fields: {},
    };
    expect(identifyInput([identify], { row: 0, col: 1, host: "192.0.2.8", local_api_key: "***" })).toEqual({
      target: "tile",
      row: 0,
      col: 1,
    });
    expect(identifyInput([identify], { row: 0, col: 1, host: "192.0.2.8", local_api_key: "k", enabled: true })).toEqual(
      {
        target: "tile",
        row: 0,
        col: 1,
        host: "192.0.2.8",
        local_api_key: "k",
      },
    );
  });
});
