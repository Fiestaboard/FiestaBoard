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
  server.use(
    http.get("/api/outputs/catalog", () =>
      HttpResponse.json({ outputs: [...installed, ...extra], registry_status: "available" }),
    ),
  );
}

function renderWizard() {
  localStorage.setItem("fiestaboard_wizard_progress", JSON.stringify({ currentStep: 1 }));
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SetupWizard />
    </QueryClientProvider>,
  );
}

async function choose(name: RegExp) {
  await userEvent.click(await screen.findByRole("radio", { name }));
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
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
    expect(await screen.findByRole("heading", { level: 1, name: "What will FiestaBoard drive?" })).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /Vestaboard/ }));
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
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
    const heading = await screen.findByRole("heading", { level: 1, name: "Connect your Vestaboard" });
    await waitFor(() => expect(heading).toHaveFocus());
  });
});

describe("the Vestaboard path", () => {
  it("tests draft settings without writing and adds a board only on Continue", async () => {
    available();
    const tests = record("post", "/api/outputs/vestaboard/actions/test_connection", () =>
      HttpResponse.json({
        status: "ok",
        message: "Board answered",
        guidance: [],
        fields: null,
        geometry: null,
        devices: null,
      }),
    );
    const boards = record("post", "/api/settings/board/add", (body) =>
      HttpResponse.json({ boards: [{ ...(body as object), id: "new-board" }] }),
    );
    const legacy = record("put", "/api/config/board", () => HttpResponse.json({}));
    renderWizard();
    await choose(/Vestaboard/);
    await userEvent.type(await screen.findByLabelText("Address"), "192.0.2.60");
    await userEvent.type(screen.getByLabelText("Local API key"), "test_key");
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Board answered");
    expect(boards).toEqual([]);
    expect(tests).toEqual([
      { output_config: expect.objectContaining({ api_mode: "local", host: "192.0.2.60", local_api_key: "test_key" }) },
    ]);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Step 3 of 4")).toBeInTheDocument();
    expect(boards).toEqual([
      expect.objectContaining({
        device_type: "flagship",
        output: "vestaboard",
        output_config: expect.objectContaining({ host: "192.0.2.60" }),
      }),
    ]);
    expect(legacy).toEqual([]);
  });
});

describe("the TV path", () => {
  it("creates on Continue, removes only the untouched placeholder and carries its name into Review", async () => {
    available();
    const created = record("post", "/api/panels", (body) =>
      HttpResponse.json({
        id: "panel-1",
        short_code: 3,
        name: (body as { name: string }).name,
        board_id: "panel-board",
      }),
    );
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          boards: [
            { id: "placeholder", name: "My Board", device_type: "flagship", output: "vestaboard", output_config: {} },
            { id: "panel-board", name: "Den TV", device_type: "panel", output: "fiestapanel" },
          ],
        }),
      ),
    );
    const removed = record("delete", "/api/settings/board/placeholder", () => HttpResponse.json({ boards: [] }));
    renderWizard();
    await choose(/FiestaPanel/);
    const name = await screen.findByLabelText("TV name");
    await userEvent.clear(name);
    await userEvent.type(name, "Den TV");
    expect(screen.getByText("How the TV connects")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Step 3 of 4")).toBeInTheDocument();
    expect(created).toEqual([{ name: "Den TV", screen_diagonal_inches: 55 }]);
    expect(removed).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Den TV")).toBeInTheDocument();
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
    await userEvent.click(screen.getByLabelText("Skip the connection test and add this community display untested"));
    await userEvent.click(screen.getByRole("button", { name: "Add board" }));

    expect(await screen.findByTestId("wizard-output-created")).toHaveTextContent("Porch sign is saved.");
    expect(boards).toEqual([{ device_model: "sign_small", output_config: { host: "192.0.2.10" }, name: "Porch sign" }]);
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
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
