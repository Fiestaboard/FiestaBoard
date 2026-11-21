/**
 * BB-C-22: the Integrations list on a phone follows Figma 324:50158 — the
 * title alone, a full-width "Installed · n | Marketplace" pair, then the
 * groups with a status dot on each row. Search and sort are left to wider
 * screens; Check for updates and Auto-update move under the list, so they
 * stay reachable.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsSection } from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const plugin = (id: string, configured = true, enabled = true) => ({
  id,
  name: id,
  category: "utility",
  version: "1.0.0",
  description: `${id} description`,
  author: "FiestaBoard",
  enabled,
  configured,
  icon: "puzzle",
  config: {},
  source: { source_type: "builtin" },
  plugin_type: "data",
  update_available: false,
  instance_label: null,
  base_plugin_id: id,
});

function phoneViewport() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.startsWith("(max-width: 767"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IntegrationsSection>
        <IntegrationsPage />
      </IntegrationsSection>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  phoneViewport();
  server.use(
    http.get("/api/plugins", () =>
      HttpResponse.json({
        plugins: [plugin("Weather"), plugin("Transit", false), plugin("Music", true, false)],
        total: 3,
        enabled_count: 2,
        plugin_system_enabled: true,
      }),
    ),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [] })),
    http.get("/api/oauth/connections", () => HttpResponse.json({ connections: [], redirect_uri: "" })),
    http.get("/api/settings/plugins", () => HttpResponse.json({ auto_update: false })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Integrations list on a phone (BB-C-22)", () => {
  it("leads with the title alone: no description and no header action", async () => {
    renderList();
    await screen.findByRole("list", { name: "Installed" });
    const header = document.querySelector<HTMLElement>("[data-slot=page-header]")!;
    expect(within(header).queryByText("Enable and configure data source plugins for your FiestaBoard")).toBeNull();
    expect(within(header).queryByRole("button", { name: /check for updates/i })).toBeNull();
  });

  it("offers Installed · n and Marketplace, and no installed search or sort", async () => {
    renderList();
    expect(await screen.findByRole("tab", { name: "Installed · 3" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Marketplace" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Search installed plugins..." })).toBeNull();
    expect(screen.queryByRole("group", { name: "Sort installed integrations" })).toBeNull();
  });

  it("leads each row with a status dot in its state's colour", async () => {
    renderList();
    const attention = await screen.findByRole("list", { name: "Needs attention" });
    const installed = screen.getByRole("list", { name: "Installed" });
    const dot = (list: HTMLElement, name: string) =>
      within(list)
        .getByRole("link", { name: new RegExp(`^${name}`) })
        .querySelector("[data-slot=status-dot]");
    expect(dot(attention, "Transit")?.className).toMatch(/warning/);
    expect(dot(installed, "Weather")?.className).toMatch(/success/);
    expect(dot(installed, "Music")?.className).not.toMatch(/success|warning/);
  });

  it("nests no listitem in another (kit 8.17.0-alpha.4 wraps render rows; axe listitem)", async () => {
    renderList();
    const installed = await screen.findByRole("list", { name: "Installed" });
    await within(installed).findByRole("link", { name: /^Weather/ });
    expect(document.querySelectorAll("li li")).toHaveLength(0);
  });

  it("keeps Check for updates and Auto-update under the list", async () => {
    renderList();
    const updates = await screen.findByRole("region", { name: "Plugin updates" });
    expect(within(updates).getByRole("button", { name: /check for updates/i })).toBeInTheDocument();
    expect(await within(updates).findByRole("switch", { name: "Auto-update plugins" })).toBeInTheDocument();
  });

  it("does not let a Marketplace search filter the installed list it hides", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(await screen.findByRole("tab", { name: "Marketplace" }));
    await user.type(screen.getByRole("textbox"), "zzz");
    await user.click(screen.getByRole("tab", { name: "Installed · 3" }));
    expect(await screen.findByRole("list", { name: "Installed" })).toBeInTheDocument();
  });
});
