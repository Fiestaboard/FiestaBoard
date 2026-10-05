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
    http.get(`${API}/outputs/available`, () => HttpResponse.json(offered)),
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
  it("offers every installed or bundled output and no way to skip", async () => {
    setup([
      ...BUILT_INS,
      available({ id: "acme_sign", name: "Acme Sign", source: "seed", installed: false }),
      available({ id: "far_sign", name: "Far Sign", source: "registry", installed: false, needs_network: true }),
    ]);
    const dialog = await screen.findByRole("dialog", { name: "Add a display" });
    expect(await within(dialog).findByRole("radio", { name: /Vestaboard/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /FiestaPanel/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /Acme Sign/ })).toBeInTheDocument();
    // A registry output is "Find more displays", not a card here.
    expect(within(dialog).queryByRole("radio", { name: /Far Sign/ })).not.toBeInTheDocument();
    expect(within(dialog).queryByTestId("wizard-skip-display")).not.toBeInTheDocument();
  });

  it("Next waits for a choice", async () => {
    setup();
    await screen.findByRole("radio", { name: /Vestaboard/ });
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("adds a Vestaboard of the shape picked and hands back its id", async () => {
    const { calls, onCreated } = setup();
    await choose(/Vestaboard/);
    expect(screen.getByRole("dialog", { name: "Add a Vestaboard" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Note" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("note-1"));
    expect(calls.add).toEqual([{ device_type: "note" }]);
  });

  it("a Note Array starts as a 2×1 cloud-mode array", async () => {
    const { calls } = setup();
    await choose(/Vestaboard/);
    await userEvent.click(screen.getByRole("button", { name: "Note Array" }));
    await waitFor(() => expect(calls.add).toHaveLength(1));
    expect(calls.add[0]).toEqual({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      output: "vestaboard",
      output_config: { api_mode: "cloud" },
    });
  });

  it("installs a bundled output when chosen, then creates its board from its own screen", async () => {
    const { calls, onCreated } = setup([
      ...BUILT_INS,
      available({ id: "acme_sign", name: "Acme Sign", source: "seed", installed: false }),
    ]);
    await choose(/Acme Sign/);
    const dialog = await screen.findByRole("dialog", { name: "Add a Acme Sign" });
    await userEvent.type(await within(dialog).findByLabelText(/Sign address/), "192.0.2.50");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add board" }));
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
    const dialog = await screen.findByRole("dialog", { name: "Add a Acme Sign" });
    await userEvent.type(await within(dialog).findByLabelText(/Sign address/), "192.0.2.50");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add board" }));
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
    expect(screen.getByRole("dialog", { name: "Add a TV or browser" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Create/ }));
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
    await userEvent.click(screen.getByRole("button", { name: /Create/ }));
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

describe("Find more displays", () => {
  function registry() {
    const entry = (id: string, name: string, plugin_type: string, installed = false) => ({
      id,
      name,
      description: `${name} plugin`,
      repository: `https://example.com/${id}`,
      branch: "main",
      author: "Example Author",
      fiestaboard_version: ">=10.0.0",
      icon: "monitor",
      category: "utility",
      installed,
      plugin_type,
      teaser: "",
      previews: [],
    });
    server.use(
      http.get(`${API}/plugins/registry`, () =>
        HttpResponse.json({
          plugin_system_enabled: true,
          entries: [
            entry("weather", "Weather", "data"),
            entry("sparkle", "Sparkle", "transition"),
            entry("far_sign", "Far Sign", "output"),
            entry("old_sign", "Old Sign", "output", true),
          ],
        }),
      ),
    );
  }

  it("lists the marketplace's display plugins not installed yet", async () => {
    setup();
    registry();
    await userEvent.click(await screen.findByTestId("find-more-displays"));
    const list = await screen.findByTestId("find-more-list");
    expect(within(list).getByRole("button", { name: /Far Sign/ })).toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: /Weather/ })).not.toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: /Sparkle/ })).not.toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: /Old Sign/ })).not.toBeInTheDocument();
  });

  it("picking one installs it and opens its screen", async () => {
    const { calls } = setup();
    registry();
    await userEvent.click(await screen.findByTestId("find-more-displays"));
    await userEvent.click(await screen.findByRole("button", { name: /Far Sign/ }));
    expect(await screen.findByRole("dialog", { name: "Add a Far Sign" })).toBeInTheDocument();
    await waitFor(() => expect(calls.install).toEqual(["far_sign"]));
    // Back from its screen goes back to the marketplace it came from.
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("dialog", { name: "Find more displays" })).toBeInTheDocument();
  });

  it("says so when the registry has none", async () => {
    setup();
    server.use(
      http.get(`${API}/plugins/registry`, () => HttpResponse.json({ plugin_system_enabled: true, entries: [] })),
    );
    await userEvent.click(await screen.findByTestId("find-more-displays"));
    expect(await screen.findByTestId("find-more-empty")).toBeInTheDocument();
  });
});
