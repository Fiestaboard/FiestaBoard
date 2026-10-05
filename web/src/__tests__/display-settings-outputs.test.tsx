/**
 * Settings → Hardware with output plugins (plan D13): a board an output plugin
 * drives renders the plugin's own screen; "Add Board" keeps the Vestaboard
 * row as it was and lists every other installed output from `GET /outputs`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { DisplaySettings } from "@/components/settings/display-settings";
import type { OutputSummary } from "@/lib/api";

import { mockOutputs } from "./mocks/handlers";
import { server } from "./mocks/server";

const API = "/api";

const PLUGIN: OutputSummary = {
  id: "acme_sign",
  name: "Acme Sign",
  description: "An LED sign on your network.",
  icon: "lightbulb",
  builtin: false,
  beta_gated: true,
  available: true,
  output_api: 1,
  capabilities: {
    technology: "led_matrix",
    delivery: "push",
    animation: "stream",
    native_transitions: [],
    charset: null,
  },
  device_models: [
    { id: "divoom_pixoo64", label: "Divoom Pixoo 64" },
    { id: "hub75_64x32", label: "HUB75 64×32" },
  ],
  settings_schema: {
    type: "object",
    properties: {
      host: { type: "string", title: "Sign address" },
      token: { type: "string", title: "Token", secret: true },
    },
    required: ["host"],
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
  ],
};

function setup(boards: Record<string, unknown>[], outputs: OutputSummary[] = [...mockOutputs, PLUGIN]) {
  const calls: { put: unknown[]; create: { url: string; body: unknown }[] } = { put: [], create: [] };
  server.use(
    http.get(`${API}/outputs`, () => HttpResponse.json(outputs)),
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards, devices: [] })),
    http.put(`${API}/settings/board`, async ({ request }) => {
      calls.put.push(await request.json());
      return HttpResponse.json({ board_type: "black", boards, devices: [] });
    }),
    http.post(`${API}/outputs/:id/boards`, async ({ request, params }) => {
      calls.create.push({ url: String(params.id), body: await request.json() });
      return HttpResponse.json({ id: "new", name: "Kitchen sign" }, { status: 201 });
    }),
    http.get(`${API}/panels`, () => HttpResponse.json({ panels: [] })),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DisplaySettings />
    </QueryClientProvider>,
  );
  return calls;
}

const VESTABOARD = {
  id: "vb",
  name: "Hall",
  device_type: "flagship",
  api_mode: "cloud",
  cloud_key: "***",
  output: "vestaboard",
};
const SIGN = {
  id: "sign",
  name: "Kitchen sign",
  device_type: "panel",
  output: "acme_sign",
  device_model: "divoom_pixoo64",
  output_config: { host: "192.0.2.50", token: "***" },
};

describe("a board an output plugin drives", () => {
  it("renders the plugin's settings screen instead of the Vestaboard form", async () => {
    setup([VESTABOARD, SIGN]);
    const cards = await screen.findAllByTestId("board-card");
    await userEvent.click(within(cards[1]).getByText("Kitchen sign"));
    expect(await within(cards[1]).findByLabelText(/Sign address/)).toHaveValue("192.0.2.50");
    expect(within(cards[1]).getByRole("button", { name: "Test connection" })).toBeInTheDocument();
    expect(within(cards[1]).queryByRole("radiogroup", { name: /API/i })).not.toBeInTheDocument();
    expect(within(cards[1]).queryByLabelText(/device type/i)).not.toBeInTheDocument();
  });

  it("saves its output_config with the board settings, secrets left masked", async () => {
    const calls = setup([VESTABOARD, SIGN]);
    const cards = await screen.findAllByTestId("board-card");
    await userEvent.click(within(cards[1]).getByText("Kitchen sign"));
    const host = await within(cards[1]).findByLabelText(/Sign address/);
    await userEvent.clear(host);
    await userEvent.type(host, "192.0.2.51");
    await userEvent.click(within(cards[1]).getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(calls.put).toHaveLength(1));
    const saved = (calls.put[0] as { boards: Record<string, unknown>[] }).boards.find((b) => b.id === "sign");
    expect(saved?.output_config).toEqual({ host: "192.0.2.51", token: "***" });
  });

  it("says so when the board's output is not installed", async () => {
    setup([VESTABOARD, SIGN], mockOutputs);
    const cards = await screen.findAllByTestId("board-card");
    await userEvent.click(within(cards[1]).getByText("Kitchen sign"));
    expect(await within(cards[1]).findByTestId("output-not-installed")).toHaveTextContent("acme_sign");
  });
});

describe("Add Board", () => {
  it("keeps the Vestaboard row and lists the other installed outputs", async () => {
    setup([VESTABOARD]);
    await userEvent.click(await screen.findByRole("button", { name: "Add Board" }));
    expect(screen.getByText("Select type:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Flagship" })).toBeInTheDocument();
    const others = await screen.findByTestId("other-output-cards");
    expect(within(others).getByRole("button", { name: "FiestaPanel" })).toBeInTheDocument();
    expect(within(others).getByRole("button", { name: "Acme Sign" })).toBeInTheDocument();
    expect(within(others).queryByRole("button", { name: "Vestaboard" })).not.toBeInTheDocument();
  });

  it("creates a plugin board from its own screen", async () => {
    const calls = setup([VESTABOARD]);
    await userEvent.click(await screen.findByRole("button", { name: "Add Board" }));
    await userEvent.click(await screen.findByRole("button", { name: "Acme Sign" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Add a Acme Sign board")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText("Board name"), "Kitchen sign");
    await userEvent.type(within(dialog).getByLabelText(/Sign address/), "192.0.2.50");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add board" }));
    await waitFor(() => expect(calls.create).toHaveLength(1));
    expect(calls.create[0]).toEqual({
      url: "acme_sign",
      body: { device_model: "divoom_pixoo64", output_config: { host: "192.0.2.50" }, name: "Kitchen sign" },
    });
  });

  it("running an action that asks for input does not create the board", async () => {
    const pair = {
      id: "pair",
      label: "Pair",
      description: "Pair using the code on the sign.",
      builtin: false,
      input_schema: {
        type: "object",
        properties: { code: { type: "string", title: "Pairing code" } },
        required: ["code"],
      },
      result_fields: {},
    };
    const actions: unknown[] = [];
    const calls = setup([VESTABOARD], [...mockOutputs, { ...PLUGIN, actions: [...PLUGIN.actions, pair] }]);
    server.use(
      http.post(`${API}/outputs/acme_sign/actions/pair`, async ({ request }) => {
        actions.push(await request.json());
        return HttpResponse.json({
          status: "ok",
          message: "Paired.",
          guidance: [],
          fields: null,
          geometry: null,
          devices: null,
        });
      }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Add Board" }));
    await userEvent.click(await screen.findByRole("button", { name: "Acme Sign" }));
    const add = await screen.findByRole("dialog");
    await userEvent.click(within(add).getByRole("button", { name: "Pair" }));
    const ask = await screen.findByRole("dialog", { name: "Pair" });
    await userEvent.type(within(ask).getByLabelText(/Pairing code/), "1234");
    await userEvent.click(within(ask).getByRole("button", { name: "Next" }));

    await waitFor(() => expect(actions).toHaveLength(1));
    expect(calls.create).toEqual([]);
    expect(await screen.findByText("Paired.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Add a Acme Sign board" })).toBeInTheDocument();
  });

  it("disables an output plugin whose beta is off, and says why", async () => {
    setup([VESTABOARD], [...mockOutputs, { ...PLUGIN, available: false }]);
    await userEvent.click(await screen.findByRole("button", { name: "Add Board" }));
    const card = await screen.findByRole("button", { name: "Acme Sign" });
    expect(card).toBeDisabled();
    expect(card).toHaveAccessibleDescription(/Settings → Beta/);
  });
});
