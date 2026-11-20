/**
 * Displays → Add a display (plan D21): the setup wizard's output-first flow
 * in a dialog — choose an output (installed or bundled), or find one in the
 * marketplace; set it up (a Vestaboard's shape, a TV's size, or an output
 * plugin's own screen after installing it); the new display's id comes back.
 */
import { Dialog } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";

import { AddDisplayDialog } from "@/components/displays/add-display-dialog";
import { PANELS_QUERY_KEY } from "@/hooks/use-panel-targets";
import type { AvailableOutput, OutputSummary } from "@/lib/api";

import { mockOutputs } from "./mocks/handlers";
import { server } from "./mocks/server";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

const API = "/api";

const SIGN: OutputSummary = {
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
  device_models: [{ id: "divoom_pixoo64", label: "Divoom Pixoo 64" }],
  settings_schema: {
    type: "object",
    properties: { host: { type: "string", title: "Sign address" } },
    required: ["host"],
  },
  actions: [],
};

function available(output: Partial<AvailableOutput> & Pick<AvailableOutput, "id" | "name">): AvailableOutput {
  return {
    description: "",
    icon: null,
    source: "installed",
    installed: true,
    builtin: false,
    beta_gated: false,
    available: true,
    needs_network: false,
    output_api: 1,
    ...output,
  };
}

const BUILT_INS = [
  available({ id: "vestaboard", name: "Vestaboard", builtin: true }),
  available({ id: "fiestapanel", name: "FiestaPanel", builtin: true }),
];

function setup(
  offered: AvailableOutput[] = BUILT_INS,
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  const calls = { add: [] as unknown[], create: [] as unknown[], install: [] as string[], removed: [] as string[] };
  server.use(
    http.get(`${API}/outputs`, () => HttpResponse.json([...mockOutputs, SIGN])),
    http.get(`${API}/outputs/catalog`, () => HttpResponse.json({ outputs: offered, registry_status: "available" })),
    http.post(`${API}/outputs/:id/install`, ({ params }) => {
      calls.install.push(String(params.id));
      return HttpResponse.json(SIGN);
    }),
    http.post(`${API}/outputs/:id/boards`, async ({ request }) => {
      calls.create.push(await request.json());
      return HttpResponse.json({ id: "sign-1", name: "Kitchen sign" }, { status: 201 });
    }),
    http.post(`${API}/settings/board/add`, async ({ request }) => {
      calls.add.push(await request.json());
      return HttpResponse.json(
        {
          board_type: "black",
          boards: [
            { id: "default", name: "My Board", device_type: "flagship", board_color: "black" },
            { id: "note-1", name: "My Board 2", device_type: "note", board_color: "black" },
          ],
          devices: ["flagship", "note"],
        },
        { status: 201 },
      );
    }),
    http.delete(`${API}/settings/board/:id`, ({ params }) => {
      calls.removed.push(String(params.id));
      return HttpResponse.json({ board_type: "black", boards: [], devices: [] });
    }),
  );
  const onCreated = vi.fn();
  const onCancel = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <Dialog open>
        <AddDisplayDialog onCreated={onCreated} onCancel={onCancel} />
      </Dialog>
    </QueryClientProvider>,
  );
  return { calls, onCreated, onCancel };
}

async function choose(name: RegExp) {
  await userEvent.click(await screen.findByRole("radio", { name }));
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
}

describe("Add a display", () => {
  it("offers local and marketplace outputs and no way to skip", async () => {
    setup([
      ...BUILT_INS,
      available({ id: "acme_sign", name: "Acme Sign", source: "seed", installed: false }),
      available({ id: "far_sign", name: "Far Sign", source: "registry", installed: false, needs_network: true }),
    ]);
    const dialog = await screen.findByRole("dialog", { name: "Add a display" });
    expect(await within(dialog).findByRole("radio", { name: /Vestaboard/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /FiestaPanel/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /Acme Sign/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /Far Sign/ })).toBeInTheDocument();
    expect(within(dialog).queryByTestId("wizard-skip-display")).not.toBeInTheDocument();
  });

  it("Next waits for a choice", async () => {
    setup();
    await screen.findByRole("radio", { name: /Vestaboard/ });
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("tests a Vestaboard connection before creating it, preserving existing displays", async () => {
    const { calls, onCreated } = setup();
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
    await choose(/Vestaboard/);
    await userEvent.type(await screen.findByLabelText("Address"), "192.0.2.70");
    await userEvent.type(screen.getByLabelText("Local API key"), "test_key");
    expect(screen.getByRole("button", { name: "Add display" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Board answered");
    expect(calls.add).toEqual([]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Add display" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Add display" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("note-1"));
    expect(calls.add).toEqual([
      expect.objectContaining({
        output: "vestaboard",
        output_config: { api_mode: "local", host: "192.0.2.70", local_api_key: "test_key" },
      }),
    ]);
  });

  it("installs a bundled output when chosen, then creates its board from its own screen", async () => {
    const { calls, onCreated } = setup([
      ...BUILT_INS,
      available({ id: "acme_sign", name: "Acme Sign", source: "seed", installed: false }),
    ]);
    await choose(/Acme Sign/);
    const dialog = await screen.findByRole("dialog", { name: "Add a display" });
    await userEvent.type(await within(dialog).findByLabelText(/Sign address/), "192.0.2.50");
    await userEvent.click(
      within(dialog).getByLabelText("Skip the connection test and add this community display untested"),
    );
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Add display" })).toBeEnabled());
    await userEvent.click(within(dialog).getByRole("button", { name: "Add display" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("sign-1"));
    expect(calls.install).toEqual(["acme_sign"]);
    expect(calls.create).toEqual([
      { device_model: "divoom_pixoo64", output_config: { host: "192.0.2.50" }, name: "Acme Sign" },
    ]);
  });

  it("never removes the placeholder board the way the first-run wizard does", async () => {
    const { calls, onCreated } = setup([
      ...BUILT_INS,
      available({ id: "acme_sign", name: "Acme Sign", source: "seed", installed: false }),
    ]);
    // The fixture's only other board is an untouched "My Board" placeholder.
    server.use(
      http.get(`${API}/settings/board`, () =>
        HttpResponse.json({
          board_type: "black",
          boards: [
            {
              id: "default",
              name: "My Board",
              device_type: "flagship",
              board_color: "black",
              output: "vestaboard",
              output_config: {},
            },
            { id: "sign-1", name: "Acme Sign", device_type: "panel", board_color: "black", output: "acme_sign" },
          ],
          devices: [],
        }),
      ),
    );
    await choose(/Acme Sign/);
    const dialog = await screen.findByRole("dialog", { name: "Add a display" });
    await userEvent.type(await within(dialog).findByLabelText(/Sign address/), "192.0.2.50");
    await userEvent.click(
      within(dialog).getByLabelText("Skip the connection test and add this community display untested"),
    );
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Add display" })).toBeEnabled());
    await userEvent.click(within(dialog).getByRole("button", { name: "Add display" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(calls.removed).toEqual([]);
  });

  it("creates a FiestaPanel from a name and a TV size", async () => {
    const created: unknown[] = [];
    const { onCreated } = setup();
    server.use(
      http.post(`${API}/panels`, async ({ request }) => {
        created.push(await request.json());
        return HttpResponse.json(
          { id: "p1", short_code: 1, name: "Living Room TV", board_id: "panel-board" },
          { status: 201 },
        );
      }),
    );
    await choose(/FiestaPanel/);
    expect(screen.getByRole("dialog", { name: "Add a display" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Add display" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Add display" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("panel-board"));
    expect(created).toHaveLength(1);
  });

  it("a new FiestaPanel refreshes the cached panel list, so its display page shows it", async () => {
    // The display page reads the panel list through PANELS_QUERY_KEY; a list
    // cached before the create must not keep saying "No panels yet".
    const panel = { id: "p1", short_code: 1, name: "Living Room TV", board_id: "panel-board" };
    let panels: (typeof panel)[] = [];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(PANELS_QUERY_KEY, { panels: [], total: 0 });
    const { onCreated } = setup(BUILT_INS, client);
    server.use(
      http.get(`${API}/panels`, () => HttpResponse.json({ panels, total: panels.length })),
      http.post(`${API}/panels`, () => {
        panels = [panel];
        return HttpResponse.json(panel, { status: 201 });
      }),
    );
    await choose(/FiestaPanel/);
    await waitFor(() => expect(screen.getByRole("button", { name: "Add display" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Add display" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("panel-board"));
    await waitFor(() => expect(client.getQueryData<{ panels: unknown[] }>(PANELS_QUERY_KEY)?.panels).toEqual([panel]));
  });

  it("Back returns to the choice", async () => {
    setup();
    await choose(/Vestaboard/);
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("dialog", { name: "Add a display" })).toBeInTheDocument();
  });

  it("Cancel leaves", async () => {
    const { onCancel } = setup();
    await screen.findByRole("radio", { name: /Vestaboard/ });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});

describe("Add a Vestaboard: address and an already connected board", () => {
  const KITCHEN = {
    id: "kitchen",
    name: "Kitchen",
    output: "vestaboard",
    device_type: "flagship",
    board_color: "black",
    output_config: { api_mode: "local", host: "192.0.2.60", local_api_key: "***" },
  };

  function knownKitchen() {
    const lookups: Record<string, unknown>[] = [];
    const writes: unknown[] = [];
    server.use(
      http.post(`${API}/config/board/existing`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        lookups.push(body);
        return HttpResponse.json({
          existing:
            body.host === "192.0.2.60"
              ? [{ board_id: "kitchen", name: "Kitchen", output: "vestaboard", matched: "host" }]
              : [],
        });
      }),
      http.get(`${API}/settings/board`, () =>
        HttpResponse.json({ board_type: "black", boards: [KITCHEN], devices: ["flagship"] }),
      ),
      http.put(`${API}/settings/board`, async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({ board_type: "black", boards: [KITCHEN], devices: ["flagship"] });
      }),
    );
    return { lookups, writes };
  }

  it("BB-C-15: an address with a port is caught at the field, not sent to the board", async () => {
    const tested = vi.fn();
    server.use(
      http.post(`${API}/outputs/vestaboard/actions/test_connection`, () => {
        tested();
        return HttpResponse.json({ detail: "host must be a bare IP address or hostname" }, { status: 400 });
      }),
    );
    setup();
    await choose(/Vestaboard/);
    const address = await screen.findByLabelText("Address");
    await userEvent.type(address, "127.0.0.1:9");
    await userEvent.type(screen.getByLabelText("Local API key"), "test_key");

    expect(address).toHaveAttribute("aria-invalid", "true");
    expect(address).toHaveAccessibleDescription(expect.stringContaining("Enter just the address, without a port."));
    expect(screen.getByRole("button", { name: "Test connection" })).toBeDisabled();
    expect(screen.queryByText("Couldn’t reach the board")).not.toBeInTheDocument();
    expect(tested).not.toHaveBeenCalled();
  });

  it("BB-C-15: an address with a port never finds an existing board", async () => {
    const { lookups } = knownKitchen();
    setup();
    await choose(/Vestaboard/);
    await userEvent.type(await screen.findByLabelText("Address"), "192.0.2.60:7000");
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(lookups.filter((query) => typeof query.host === "string" && query.host.includes(":"))).toEqual([]);
    expect(screen.queryByText("This board is already connected")).not.toBeInTheDocument();
  });

  it("BB-C-15: a hostname or IP address is accepted", async () => {
    setup();
    await choose(/Vestaboard/);
    const address = await screen.findByLabelText("Address");
    await userEvent.type(address, "vestaboard-kitchen.local");
    await userEvent.type(screen.getByLabelText("Local API key"), "test_key");
    expect(address).not.toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Test connection" })).toBeEnabled();
  });

  it("BB-C-16: keeping the board already connected reads Go to <name> and says nothing was added", async () => {
    vi.mocked(toast.success).mockClear();
    const { writes } = knownKitchen();
    const { calls, onCreated } = setup();
    await choose(/Vestaboard/);
    await userEvent.type(await screen.findByLabelText("Address"), "192.0.2.60");
    expect(await screen.findByText("This board is already connected")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Add display" })).not.toBeInTheDocument();
    const go = await screen.findByRole("button", { name: "Go to Kitchen" });
    await waitFor(() => expect(go).toBeEnabled());
    await userEvent.click(go);

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("kitchen"));
    expect(calls.add).toEqual([]);
    expect(writes).toEqual([]);
    expect(toast.info).toHaveBeenCalledWith("Nothing added · Kitchen is already connected");
    expect(toast.success).not.toHaveBeenCalledWith(expect.stringContaining("added"));
  });

  it("BB-C-16: choosing to update the board already connected says so", async () => {
    knownKitchen();
    setup();
    await choose(/Vestaboard/);
    await userEvent.type(await screen.findByLabelText("Address"), "192.0.2.60");
    await userEvent.click(await screen.findByRole("radio", { name: /Update its connection/ }));
    expect(await screen.findByRole("button", { name: "Update Kitchen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add display" })).not.toBeInTheDocument();
  });
});

describe("marketplace displays in the shared chooser", () => {
  const remote = available({
    id: "far_sign",
    name: "Far Sign",
    installed: false,
    source: "registry",
    needs_network: true,
  });
  it("offers marketplace plugins alongside local displays", async () => {
    setup([...BUILT_INS, remote]);
    expect(await screen.findByRole("radio", { name: /Far Sign/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Vestaboard/ })).toBeInTheDocument();
  });
  it("installs the selected plugin and returns to the same chooser", async () => {
    const { calls } = setup([...BUILT_INS, remote]);
    await userEvent.click(await screen.findByRole("radio", { name: /Far Sign/ }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("dialog", { name: "Add a display" })).toBeInTheDocument();
    await waitFor(() => expect(calls.install).toEqual(["far_sign"]));
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("radio", { name: /Far Sign/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });
});
