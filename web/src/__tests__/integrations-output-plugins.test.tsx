/**
 * Output plugins on the Integrations page, and their beta switch.
 *
 * An output plugin drives a board that names it as its output; the plugin
 * registry's enabled flag means nothing for it. Like a transition, it gets a
 * type badge ("Output") in place of the enable switch and the
 * enabled/disabled status — in the Installed table and in the Marketplace.
 * The page's toolbar carries the switch that lets third-party outputs drive
 * boards (`plugins.output_plugins_enabled`; Settings → Beta until settings
 * v6). An output plugin a board uses cannot be
 * uninstalled; the page shows the server's reason, naming the boards. A
 * first-party output (`required`: Vestaboard, FiestaPanel) updates here like
 * any plugin but offers no uninstall at all.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { PluginUpdatesControl } from "../components/plugin-updates-control";
import { server } from "./mocks/server";

const API_BASE = "/api";

const toastMock = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn(), error: vi.fn(), warning: vi.fn() }));

vi.mock("sonner", () => ({ toast: toastMock, Toaster: () => null }));

function mockInstalled(plugin_type: "data" | "output", extra: Record<string, unknown> = {}) {
  const plugin = {
    id: "acme_sign",
    name: "Acme Sign",
    version: "1.0.0",
    description: "Acme Sign description",
    author: "FiestaBoard",
    enabled: false,
    configured: false,
    icon: "puzzle",
    category: plugin_type === "output" ? "output" : "utility",
    plugin_type,
    config: {},
    source: { source_type: "registry" as const },
    update_available: false,
    instance_label: null,
    base_plugin_id: "acme_sign",
    settings_schema: {},
    ...extra,
  };
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins: [plugin], plugin_system_enabled: true, total: 1, enabled_count: 0 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: [] })),
  );
}

function renderWithQuery(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

async function rowFor(name: string): Promise<HTMLElement> {
  const row = (await screen.findByText(name)).closest("tr");
  if (!row) throw new Error(`No table row for ${name}`);
  return row as HTMLElement;
}

describe("Integrations page — output plugins", () => {
  it("renders no enable switch and no enabled/disabled status for an output plugin", async () => {
    mockInstalled("output");
    renderWithQuery(<IntegrationsPage />);

    const row = await rowFor("Acme Sign");
    expect(within(row).getByText("Output")).toBeInTheDocument();
    expect(within(row).queryByRole("switch")).not.toBeInTheDocument();
    expect(within(row).queryByText("Disabled")).not.toBeInTheDocument();
  });

  it("labels the output category with its translated name", async () => {
    mockInstalled("output");
    renderWithQuery(<IntegrationsPage />);

    const row = await rowFor("Acme Sign");
    expect(within(row).getByText("Outputs")).toBeInTheDocument();
  });

  it("keeps the switch for the same plugin as a data plugin (control)", async () => {
    mockInstalled("data");
    renderWithQuery(<IntegrationsPage />);

    const row = await rowFor("Acme Sign");
    expect(within(row).getByRole("switch")).toBeInTheDocument();
    expect(within(row).queryByText("Output")).not.toBeInTheDocument();
  });

  it("badges a Marketplace entry whose plugin_type is output", async () => {
    server.use(
      http.get(`${API_BASE}/plugins`, () =>
        HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 }),
      ),
      http.get(`${API_BASE}/plugins/registry`, () =>
        HttpResponse.json({
          entries: [
            {
              id: "acme_sign",
              name: "Acme Sign",
              description: "Acme Sign description",
              repository: "https://example.com/fiestaboard-output--acme-sign",
              branch: "main",
              author: "FiestaBoard",
              fiestaboard_version: ">=10.0.0",
              icon: "puzzle",
              category: "output",
              plugin_type: "output",
              installed: false,
              teaser: "",
              previews: [],
            },
          ],
        }),
      ),
    );
    renderWithQuery(<IntegrationsPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /marketplace/i }));
    await user.click(await screen.findByRole("button", { name: /list view/i }));

    const row = await rowFor("Acme Sign");
    expect(within(row).getByText("Output")).toBeInTheDocument();
  });
});

describe("Integrations page — uninstalling an output plugin a board uses", () => {
  it("shows the server's reason, naming the boards", async () => {
    mockInstalled("output");
    const reason =
      "Output plugin 'acme_sign' drives 1 board(s): 'Kitchen'. " +
      "Switch those boards to another output, or delete them, before uninstalling it.";
    server.use(
      http.delete(`${API_BASE}/plugins/acme_sign/uninstall`, () =>
        HttpResponse.json({ detail: reason }, { status: 400 }),
      ),
    );
    renderWithQuery(<IntegrationsPage />);
    const user = userEvent.setup();

    const row = await rowFor("Acme Sign");
    await user.click(within(row).getByRole("button", { name: "More options" }));
    await user.click(await screen.findByRole("menuitem", { name: /delete/i }));
    await user.click(await screen.findByRole("button", { name: /delete/i }));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(`Failed to uninstall acme_sign: ${reason}`));
    expect(toastMock.success).not.toHaveBeenCalled();
  });
});

describe("Integrations page — a first-party output (required)", () => {
  it("offers its update but no way to uninstall it", async () => {
    mockInstalled("output", { required: true, update_available: true });
    renderWithQuery(<IntegrationsPage />);
    const user = userEvent.setup();

    const row = await rowFor("Acme Sign");
    expect(within(row).getByText("Update")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "More options" }));
    expect(await screen.findByRole("menu")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("still offers uninstall for an output plugin that is not required (control)", async () => {
    mockInstalled("output", { required: false });
    renderWithQuery(<IntegrationsPage />);
    const user = userEvent.setup();

    const row = await rowFor("Acme Sign");
    await user.click(within(row).getByRole("button", { name: "More options" }));
    expect(await screen.findByRole("menuitem", { name: /delete/i })).toBeInTheDocument();
  });
});

describe("Integrations toolbar — third-party displays", () => {
  it("turns output plugins on", async () => {
    let body: unknown = null;
    server.use(
      http.put(`${API_BASE}/settings/plugins`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          auto_update: true,
          transition_plugins_enabled: false,
          output_plugins_enabled: true,
        });
      }),
    );
    renderWithQuery(<PluginUpdatesControl />);

    const toggle = await screen.findByRole("switch", { name: "Third-party displays (beta)" });
    expect(toggle).not.toBeChecked();
    await userEvent.setup().click(toggle);
    await waitFor(() => expect(body).toEqual({ output_plugins_enabled: true }));
  });
});
