/**
 * Transition plugins on the Integrations page.
 *
 * `PluginRegistry.get_transition_plugin()` never consults the enabled flag —
 * a transition runs as soon as it is installed and selected. Rendering the
 * usual enable/disable Switch for one therefore promises control the backend
 * does not honour. These tests pin the corrected presentation: transition
 * plugins get a "Transition" badge instead of a toggle and instead of an
 * enabled/disabled status, while ordinary data plugins keep both.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

interface MockPlugin {
  id: string;
  name: string;
  category: string;
  plugin_type?: "data" | "transition";
  enabled?: boolean;
  configured?: boolean;
}

function mockPlugins(plugins: MockPlugin[]) {
  const full = plugins.map((p) => ({
    version: "1.0.0",
    description: `${p.name} description`,
    author: "FiestaBoard",
    enabled: true,
    configured: true,
    icon: "puzzle",
    config: {},
    source: { source_type: "builtin" as const },
    update_available: false,
    instance_label: null,
    base_plugin_id: p.id,
    settings_schema: {},
    ...p,
  }));
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({
        plugins: full,
        plugin_system_enabled: true,
        total: full.length,
        enabled_count: full.filter((p) => p.enabled).length,
      }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: [] })),
  );
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <IntegrationsPage />
    </QueryClientProvider>,
  );
}

/** The installed-table row whose Name cell holds `name`. */
async function rowFor(name: string): Promise<HTMLElement> {
  const cell = await screen.findByText(name);
  const row = cell.closest("tr");
  if (!row) throw new Error(`No table row found for plugin "${name}"`);
  return row as HTMLElement;
}

describe("Integrations page — transition plugins", () => {
  it("renders no enable toggle for a transition plugin", async () => {
    mockPlugins([{ id: "typewriter", name: "Typewriter", category: "transition", plugin_type: "transition" }]);
    renderPage();

    const row = await rowFor("Typewriter");
    expect(within(row).queryByRole("switch")).not.toBeInTheDocument();
  });

  it("badges a transition plugin as a Transition", async () => {
    mockPlugins([{ id: "typewriter", name: "Typewriter", category: "transition", plugin_type: "transition" }]);
    renderPage();

    const row = await rowFor("Typewriter");
    expect(within(row).getByText("Transition")).toBeInTheDocument();
  });

  it("shows no enabled/disabled status for a transition plugin", async () => {
    mockPlugins([
      {
        id: "typewriter",
        name: "Typewriter",
        category: "transition",
        plugin_type: "transition",
        enabled: false,
        configured: false,
      },
    ]);
    renderPage();

    const row = await rowFor("Typewriter");
    expect(within(row).queryByText("Disabled")).not.toBeInTheDocument();
    expect(within(row).queryByText("Configured")).not.toBeInTheDocument();
    expect(within(row).queryByText("Setup Required")).not.toBeInTheDocument();
  });

  it("labels the transition category with its translated name", async () => {
    mockPlugins([{ id: "typewriter", name: "Typewriter", category: "transition", plugin_type: "transition" }]);
    renderPage();

    const row = await rowFor("Typewriter");
    expect(within(row).getByText("Transitions")).toBeInTheDocument();
  });

  it("still renders the enable toggle for a data plugin", async () => {
    mockPlugins([{ id: "weather", name: "Weather", category: "weather", plugin_type: "data" }]);
    renderPage();

    const row = await rowFor("Weather");
    expect(within(row).getByRole("switch")).toBeInTheDocument();
    expect(within(row).queryByText("Transition")).not.toBeInTheDocument();
  });

  it("treats a plugin with no plugin_type as a data plugin", async () => {
    mockPlugins([{ id: "weather", name: "Weather", category: "weather" }]);
    renderPage();

    const row = await rowFor("Weather");
    expect(within(row).getByRole("switch")).toBeInTheDocument();
  });

  it("keeps the Configure action available on a transition plugin", async () => {
    mockPlugins([{ id: "typewriter", name: "Typewriter", category: "transition", plugin_type: "transition" }]);
    renderPage();

    const row = await rowFor("Typewriter");
    await waitFor(() => {
      expect(within(row).getByRole("button", { name: /more options/i })).toBeInTheDocument();
    });
  });
});
