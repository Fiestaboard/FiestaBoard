/**
 * A display an output plugin drives (plans D13, D21): its page renders the
 * plugin's own settings screen. Adding one is add-display-dialog.test.tsx's.
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

const PLUGIN: OutputSummary = {
  id: "acme_sign",
  name: "Acme Sign",
  description: "An LED sign on your network.",
  icon: "lightbulb",
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
  const calls: { put: unknown[] } = { put: [] };
  server.use(
    http.get(`${API}/outputs`, () => HttpResponse.json(outputs)),
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards, devices: [] })),
    http.put(`${API}/settings/board`, async ({ request }) => {
      calls.put.push(await request.json());
      return HttpResponse.json({ board_type: "black", boards, devices: [] });
    }),
    http.get(`${API}/panels`, () => HttpResponse.json({ panels: [] })),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DisplayEditor boardId="sign" />
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

describe("a display an output plugin drives", () => {
  it("renders the plugin's settings screen instead of the Vestaboard form", async () => {
    setup([VESTABOARD, SIGN]);
    const card = await screen.findByTestId("board-card");
    expect(await within(card).findByLabelText(/Sign address/)).toHaveValue("192.0.2.50");
    expect(within(card).getByRole("button", { name: "Test connection" })).toBeInTheDocument();
    expect(within(card).queryByRole("radiogroup", { name: /API/i })).not.toBeInTheDocument();
    expect(within(card).queryByLabelText(/device type/i)).not.toBeInTheDocument();
  });

  it("saves its output_config with the board settings, secrets left masked", async () => {
    const calls = setup([VESTABOARD, SIGN]);
    const card = await screen.findByTestId("board-card");
    const host = await within(card).findByLabelText(/Sign address/);
    await userEvent.clear(host);
    await userEvent.type(host, "192.0.2.51");
    await userEvent.click(within(card).getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(calls.put).toHaveLength(1));
    const saved = (calls.put[0] as { boards: Record<string, unknown>[] }).boards.find((b) => b.id === "sign");
    expect(saved?.output_config).toEqual({ host: "192.0.2.51", token: "***" });
  });

  it("says so when the board's output is not installed", async () => {
    setup([VESTABOARD, SIGN], mockOutputs);
    const card = await screen.findByTestId("board-card");
    expect(await within(card).findByTestId("output-not-installed")).toHaveTextContent("acme_sign");
  });
});
