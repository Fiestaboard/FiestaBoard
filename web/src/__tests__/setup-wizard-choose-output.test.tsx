/**
 * The setup wizard asks what FiestaBoard will show on first (plan D18):
 * cards from `GET /outputs/available`, a first-class "add a display later",
 * then the chosen display's own set-up step — the existing Vestaboard step,
 * a TV step (`POST /panels`), or an output plugin installed on the spot and
 * set up through its own board settings screen (`POST /outputs/{id}/boards`).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SetupWizard } from "@/components/wizard";
import type { AvailableOutput, OutputSummary } from "@/lib/api";

import { mockOutputs } from "./mocks/handlers";
import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

const SIGN: OutputSummary = {
  id: "recording_sign",
  name: "Recording Sign",
  description: "An LED sign for tests.",
  icon: "lightbulb",
  builtin: false,
  beta_gated: true,
  available: true,
  output_api: 1,
  capabilities: { technology: "led", delivery: "push", animation: "none", native_transitions: [], charset: null },
  device_models: [
    { id: "sign_small", label: "Small sign" },
    { id: "sign_large", label: "Large sign" },
  ],
  settings_schema: {
    type: "object",
    properties: { host: { type: "string", title: "Sign address" } },
  },
  actions: [
    {
      id: "test_connection",
      label: "Test sign",
      description: "",
      builtin: true,
      input_schema: null,
      result_fields: {},
    },
  ],
};

const SIGN_AVAILABLE: AvailableOutput = {
  id: SIGN.id,
  name: SIGN.name,
  description: SIGN.description,
  icon: SIGN.icon,
  source: "seed",
  installed: false,
  builtin: false,
  beta_gated: false,
  available: true,
  needs_network: false,
  output_api: 1,
};

function available(extra: AvailableOutput[] = []) {
  const installed: AvailableOutput[] = mockOutputs.map((o) => ({
    id: o.id,
    name: o.name,
    description: o.description,
    icon: o.icon,
    source: "installed",
    installed: true,
    builtin: o.builtin,
    beta_gated: o.beta_gated,
    available: o.available,
    needs_network: false,
    output_api: o.output_api,
  }));
  server.use(http.get("/api/outputs/available", () => HttpResponse.json([...installed, ...extra])));
}

function renderWizard() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SetupWizard />
    </QueryClientProvider>,
  );
}

async function choose(name: RegExp) {
  await userEvent.click(await screen.findByRole("radio", { name }));
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
}

/** Requests the wizard made to `path` (method + body). */
function record(method: "post" | "put" | "delete", path: string, respond: (body: unknown) => Response) {
  const calls: unknown[] = [];
  server.use(
    http[method](path, async ({ request }) => {
      const text = await request.text();
      const body = text ? JSON.parse(text) : null;
      calls.push(body);
      return respond(body);
    }),
  );
  return calls;
}

beforeEach(() => {
  localStorage.clear();
});

describe("choosing the display", () => {
  it("opens on the question, with a card per available output", async () => {
    available([SIGN_AVAILABLE]);
    renderWizard();
    expect(
      await screen.findByRole("heading", { level: 2, name: "What do you want to show FiestaBoard on?" }),
    ).toBeInTheDocument();
    const group = await screen.findByRole("radiogroup", { name: "Displays" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((r) => r.textContent),
    ).toEqual([
      expect.stringContaining("Vestaboard"),
      expect.stringContaining("FiestaPanel"),
      expect.stringContaining("Recording Sign"),
    ]);
  });

  it("keeps Next disabled until a display is chosen", async () => {
    available();
    renderWizard();
    await screen.findByRole("radiogroup", { name: "Displays" });
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /Vestaboard/ }));
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("says which display downloads, and never asks for an opt-in", async () => {
    available([
      // What a pre-v7 server said about a marketplace display: the wizard no
      // longer reads these deprecated fields.
      { ...SIGN_AVAILABLE, source: "registry", beta_gated: true, available: false },
      { ...SIGN_AVAILABLE, id: "far_sign", name: "Far Sign", source: "registry", needs_network: true },
    ]);
    renderWizard();
    expect(await screen.findByRole("radio", { name: /Far Sign/ })).toHaveTextContent("needs an internet connection");
    expect(screen.getByRole("radio", { name: /Recording Sign/ })).not.toHaveTextContent(/beta/i);
  });

  it("'I'll add a display later' ends the wizard as skipped", async () => {
    available();
    const recorded = record("put", "/api/settings/wizard", (body) => HttpResponse.json(body as object));
    renderWizard();
    await userEvent.click(await screen.findByRole("button", { name: /I'll add a display later/ }));
    await waitFor(() => expect(recorded).toEqual([{ state: "skipped" }]));
  });

  it("moves focus to the next step's heading", async () => {
    available();
    renderWizard();
    await choose(/Vestaboard/);
    const heading = await screen.findByRole("heading", { level: 2, name: "Connect Your Board" });
    await waitFor(() => expect(heading).toHaveFocus());
  });
});

describe("the Vestaboard path", () => {
  it("leads to the existing connect step, which still offers Skip for now", async () => {
    available();
    const recorded = record("put", "/api/settings/wizard", (body) => HttpResponse.json(body as object));
    renderWizard();
    await choose(/Vestaboard/);
    expect(await screen.findByRole("heading", { name: "Connect Your Board" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Skip for now" }));
    await waitFor(() => expect(recorded).toEqual([{ state: "skipped" }]));
  });

  it("saves the board through the board store and never the deprecated PUT /config/board", async () => {
    available();
    const tests = record("post", "/api/outputs/vestaboard/actions/test_connection", () =>
      HttpResponse.json({
        status: "ok",
        message: "Successfully connected to your board!",
        guidance: [],
        fields: null,
        geometry: null,
        devices: null,
      }),
    );
    const boards = record("put", "/api/settings/board", (body) =>
      HttpResponse.json({ board_type: "black", boards: (body as { boards: unknown[] }).boards, devices: ["flagship"] }),
    );
    const legacy = record("put", "/api/config/board", () => HttpResponse.json({}));
    renderWizard();
    await choose(/Vestaboard/);
    // The Vestaboard's own settings screen, on draft settings: cloud by default.
    await userEvent.type(await screen.findByLabelText(/Read\/Write API Key/), "test_cloud_key");
    await userEvent.click(screen.getByRole("button", { name: "Test Connection" }));
    await waitFor(() => expect(boards).toHaveLength(1));
    expect(tests).toEqual([{ output_config: { api_mode: "cloud", cloud_key: "test_cloud_key" } }]);
    const saved = (boards[0] as { boards: Array<Record<string, unknown>> }).boards[0];
    expect(saved).toMatchObject({
      output: "vestaboard",
      output_config: { api_mode: "cloud", cloud_key: "test_cloud_key" },
      device_type: "flagship",
      enabled: true,
    });
    expect(saved).not.toHaveProperty("cloud_key");
    expect(await screen.findByText("Connected! Your board is saved.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeEnabled());
    expect(legacy).toEqual([]);
  });

  it("connects a board over the Local API with the type, colour and flap chosen", async () => {
    available();
    const tests = record("post", "/api/outputs/vestaboard/actions/test_connection", () =>
      HttpResponse.json({
        status: "ok",
        message: "Successfully connected to your board!",
        guidance: [],
        fields: null,
        geometry: null,
        devices: null,
      }),
    );
    const boards = record("put", "/api/settings/board", (body) =>
      HttpResponse.json({ board_type: "black", boards: (body as { boards: unknown[] }).boards, devices: ["flagship"] }),
    );
    renderWizard();
    await choose(/Vestaboard/);
    await userEvent.click(await screen.findByRole("radio", { name: /Local API/ }));
    await userEvent.type(screen.getByLabelText(/Board IP Address/), "192.168.0.50");
    await userEvent.type(screen.getByLabelText(/Local API Key/), "test-local-key");
    await userEvent.click(screen.getByTestId("wizard-code62-heart"));
    await userEvent.click(screen.getByRole("button", { name: "White" }));
    await userEvent.click(screen.getByRole("button", { name: "Test Connection" }));
    await waitFor(() => expect(boards).toHaveLength(1));

    expect(tests).toEqual([
      { output_config: { api_mode: "local", host: "192.168.0.50", local_api_key: "test-local-key" } },
    ]);
    expect((boards[0] as { boards: Array<Record<string, unknown>> }).boards[0]).toMatchObject({
      output: "vestaboard",
      output_config: { api_mode: "local", host: "192.168.0.50", local_api_key: "test-local-key" },
      board_color: "white",
      code62_glyph: "heart",
    });
  });

  it("a failed test saves nothing and keeps Next disabled", async () => {
    available();
    record("post", "/api/outputs/vestaboard/actions/test_connection", () =>
      HttpResponse.json({
        status: "error",
        message: "Your API key was rejected by the Vestaboard cloud service (HTTP 401).",
        guidance: ["Check the key in the Vestaboard app."],
        fields: null,
        geometry: null,
        devices: null,
      }),
    );
    const boards = record("put", "/api/settings/board", () => HttpResponse.json({}));
    renderWizard();
    await choose(/Vestaboard/);
    await userEvent.type(await screen.findByLabelText(/Read\/Write API Key/), "test_bad_key");
    await userEvent.click(screen.getByRole("button", { name: "Test Connection" }));

    expect(await screen.findByText("Check the key in the Vestaboard app.")).toBeInTheDocument();
    expect(boards).toEqual([]);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});

describe("the TV path", () => {
  it("creates a panel, removes the untouched placeholder board and shows the TV address", async () => {
    available();
    const created = record("post", "/api/panels", (body) =>
      HttpResponse.json(
        {
          id: "panel-1",
          short_code: 3,
          name: (body as { name: string }).name,
          board_id: "panel-board",
          screen_diagonal_inches: (body as { screen_diagonal_inches: number }).screen_diagonal_inches,
        },
        { status: 201 },
      ),
    );
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          board_type: "black",
          boards: [
            { id: "placeholder", name: "My Board", device_type: "flagship", api_mode: "local", host: "" },
            { id: "panel-board", name: "Den TV (Panel)", device_type: "panel", api_mode: "virtual", host: "" },
          ],
          devices: ["flagship"],
        }),
      ),
    );
    const removed: string[] = [];
    server.use(
      http.delete("/api/settings/board/:boardId", ({ params }) => {
        removed.push(String(params.boardId));
        return HttpResponse.json({ board_type: "black", boards: [], devices: [] });
      }),
    );
    renderWizard();
    await choose(/FiestaPanel/);
    expect(await screen.findByRole("heading", { name: "Set Up Your TV" })).toBeInTheDocument();
    const name = screen.getByLabelText("TV name");
    await userEvent.clear(name);
    await userEvent.type(name, "Den TV");
    const size = screen.getByLabelText("Screen size (inches, measured diagonally)");
    await userEvent.clear(size);
    await userEvent.type(size, "65");
    await userEvent.click(screen.getByRole("button", { name: "Create TV board" }));

    expect(await screen.findByTestId("wizard-panel-created")).toHaveTextContent("/p/3");
    expect(created).toEqual([{ name: "Den TV", screen_diagonal_inches: 65 }]);
    expect(removed).toEqual(["placeholder"]);
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();

    // The last step sums up the TV, not a Vestaboard connection.
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { level: 2, name: "Add Data Sources" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Den TV (FiestaPanel) is set up")).toBeInTheDocument();
  });

  it("refuses a screen size outside the range before calling the server", async () => {
    available();
    const created = record("post", "/api/panels", () => HttpResponse.json({}, { status: 201 }));
    renderWizard();
    await choose(/FiestaPanel/);
    const size = await screen.findByLabelText("Screen size (inches, measured diagonally)");
    await userEvent.clear(size);
    await userEvent.type(size, "500");
    expect(size).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Create TV board" })).toBeDisabled();
    expect(created).toEqual([]);
  });
});

describe("an output plugin", () => {
  function signInstalls(status = 201) {
    return record("post", `/api/outputs/${SIGN.id}/install`, () => HttpResponse.json(SIGN, { status }));
  }

  it("installs, renders its own settings screen and creates the board", async () => {
    available([SIGN_AVAILABLE]);
    const installs = signInstalls();
    const boards = record("post", `/api/outputs/${SIGN.id}/boards`, (body) =>
      HttpResponse.json(
        {
          id: "sign-board",
          name: (body as { name: string }).name,
          output: SIGN.id,
          device_model: "sign_large",
          charset: null,
          device_type: "panel",
          rows: 4,
          cols: 16,
          output_config: (body as { output_config: object }).output_config,
        },
        { status: 201 },
      ),
    );
    renderWizard();
    await choose(/Recording Sign/);
    expect(await screen.findByRole("heading", { name: "Set Up Recording Sign" })).toBeInTheDocument();
    expect(await screen.findByTestId("plugin-board-settings")).toBeInTheDocument();
    expect(installs).toHaveLength(1);
    // The plugin's own action buttons render on the draft settings.
    expect(screen.getByRole("button", { name: "Test sign" })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Sign address"), "192.0.2.10");
    const name = screen.getByLabelText("Board name");
    await userEvent.clear(name);
    await userEvent.type(name, "Porch sign");
    await userEvent.click(screen.getByRole("button", { name: "Add board" }));

    expect(await screen.findByTestId("wizard-output-created")).toHaveTextContent("Porch sign is saved and ready.");
    expect(boards).toEqual([{ device_model: "sign_small", output_config: { host: "192.0.2.10" }, name: "Porch sign" }]);
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("previews a built-in LED device as its matrix, showing the board's name", async () => {
    available([SIGN_AVAILABLE]);
    const pixoo = { ...SIGN, device_models: [{ id: "divoom_pixoo64", label: "Pixoo 64" }] };
    record("post", `/api/outputs/${SIGN.id}/install`, () => HttpResponse.json(pixoo, { status: 201 }));
    renderWizard();
    await choose(/Recording Sign/);
    const preview = await screen.findByTestId("wizard-output-device-preview");
    expect(preview.querySelector('[data-slot="display-preview"]')).toHaveAttribute("data-model", "divoom_pixoo64");
    expect(within(preview).getByRole("img").getAttribute("aria-label")).toContain("Recording Sign");
  });

  it("previews a new LED board in the face it will be created in", async () => {
    // A new Pixoo board is created Large (5x7, 8x10), not in the model's own
    // small 3x5 face: core names the new-board face per device model.
    available([SIGN_AVAILABLE]);
    const pixoo = {
      ...SIGN,
      device_models: [{ id: "divoom_pixoo64", label: "Pixoo 64", new_board_font: "5x7", new_board_charset: "led_5x7" }],
    };
    record("post", `/api/outputs/${SIGN.id}/install`, () => HttpResponse.json(pixoo, { status: 201 }));
    renderWizard();
    await choose(/Recording Sign/);
    const preview = await screen.findByTestId("wizard-output-device-preview");
    expect(preview.querySelector("[data-font]")).toHaveAttribute("data-font", "5x7");
  });

  it("shows no device preview for a plugin's own model it cannot resolve", async () => {
    available([SIGN_AVAILABLE]);
    signInstalls();
    renderWizard();
    await choose(/Recording Sign/);
    await screen.findByTestId("plugin-board-settings");
    expect(screen.queryByTestId("wizard-output-device-preview")).not.toBeInTheDocument();
  });

  it("runs the plugin's actions on the draft route", async () => {
    available([SIGN_AVAILABLE]);
    signInstalls();
    const actions = record("post", `/api/outputs/${SIGN.id}/actions/test_connection`, () =>
      HttpResponse.json({
        status: "ok",
        message: "Sign answered.",
        guidance: [],
        fields: null,
        geometry: null,
        devices: null,
      }),
    );
    renderWizard();
    await choose(/Recording Sign/);
    await userEvent.type(await screen.findByLabelText("Sign address"), "192.0.2.10");
    await userEvent.click(screen.getByRole("button", { name: "Test sign" }));
    expect(await screen.findByTestId("action-result")).toHaveTextContent("Sign answered.");
    expect(actions).toEqual([{ output_config: { host: "192.0.2.10" }, device_model: "sign_small" }]);
  });

  it("installs a marketplace display straight into its settings, with no opt-in", async () => {
    // Settings v7: a registry output installs like a bundled one.
    available([{ ...SIGN_AVAILABLE, source: "registry", needs_network: true }]);
    server.use(http.post(`/api/outputs/${SIGN.id}/install`, () => HttpResponse.json(SIGN, { status: 201 })));
    const settingsWrites = record("put", "/api/settings/plugins", (body) => HttpResponse.json(body as object));
    renderWizard();
    await choose(/Recording Sign/);
    expect(await screen.findByTestId("plugin-board-settings")).toBeInTheDocument();
    expect(settingsWrites).toEqual([]);
  });

  it("a refused install shows the server's reason and never offers an opt-in", async () => {
    // A 409 used to mean "turn on the output plugins beta"; no such switch
    // exists any more, so any refusal is the server's own reason.
    available([{ ...SIGN_AVAILABLE, source: "registry", needs_network: true }]);
    server.use(
      http.post(`/api/outputs/${SIGN.id}/install`, () =>
        HttpResponse.json({ detail: "Recording Sign is already being installed" }, { status: 409 }),
      ),
    );
    renderWizard();
    await choose(/Recording Sign/);
    const failure = await screen.findByTestId("wizard-output-install-error");
    expect(failure).toHaveAttribute("data-kind", "refused");
    expect(failure).toHaveTextContent("Recording Sign is already being installed");
    expect(
      within(failure)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["Try again"]);
  });

  it("says when the display could not be downloaded, and retries", async () => {
    available([SIGN_AVAILABLE]);
    let offline = true;
    server.use(
      http.post(`/api/outputs/${SIGN.id}/install`, () =>
        offline
          ? HttpResponse.json({ detail: "Could not download 'recording_sign'" }, { status: 503 })
          : HttpResponse.json(SIGN, { status: 201 }),
      ),
    );
    renderWizard();
    await choose(/Recording Sign/);
    const failure = await screen.findByTestId("wizard-output-install-error");
    expect(failure).toHaveAttribute("data-kind", "offline");
    expect(failure).toHaveTextContent("Check this device's internet connection");
    offline = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("plugin-board-settings")).toBeInTheDocument();
  });

  it("shows the server's reason when the plugin cannot run here", async () => {
    available([SIGN_AVAILABLE]);
    server.use(
      http.post(`/api/outputs/${SIGN.id}/install`, () =>
        HttpResponse.json({ detail: "output.output_api 99 is not supported by this FiestaBoard" }, { status: 400 }),
      ),
    );
    renderWizard();
    await choose(/Recording Sign/);
    const failure = await screen.findByTestId("wizard-output-install-error");
    expect(failure).toHaveAttribute("data-kind", "refused");
    expect(failure).toHaveTextContent("output_api 99 is not supported");
  });
});
