import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

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
  update_available: false,
  instance_label: null,
  base_plugin_id: id,
});
function mockApi() {
  const plugins = [plugin("Weather"), plugin("Transit", false), plugin("Calendar"), plugin("Music", false, false)];
  server.use(
    http.get("/api/plugins", () =>
      HttpResponse.json({ plugins, total: 4, enabled_count: 3, plugin_system_enabled: true }),
    ),
    http.get("/api/plugins/registry", () =>
      HttpResponse.json({
        entries: [
          {
            id: "new-transit",
            name: "New transit",
            description: "Arrivals",
            category: "transit",
            repository: "https://example.com/transit",
            branch: "main",
            author: "Example",
            icon: "train",
            installed: false,
          },
        ],
      }),
    ),
    http.get("/api/oauth/connections", () =>
      HttpResponse.json({
        connections: [
          {
            id: "Calendar",
            plugin_id: "Calendar",
            plugin_name: "Calendar",
            provider_name: "Example Calendar",
            status: "reauthorization_required",
            configured: true,
            flows: ["relay"],
            user_app: false,
            shared_app: true,
            scopes: [],
            expires_at: null,
            connected_at: null,
            device: null,
          },
        ],
        redirect_uri: "https://example.com/return",
      }),
    ),
    http.get("/api/v1/plugins/:id", ({ params }) =>
      HttpResponse.json({
        ...plugin(String(params.id)),
        settings_schema: { type: "object", properties: { stop: { type: "string", title: "Stop" } } },
        variables: {},
        env_vars: [],
        has_demo: false,
        config: { stop: "Central" },
      }),
    ),
    http.get("/api/v1/plugins/:id/data", ({ params }) =>
      HttpResponse.json({ plugin_id: params.id, available: false, data: {} }),
    ),
  );
}
function renderPage() {
  mockApi();
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <IntegrationsPage />
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("Integrations canonical groups", () => {
  it("announces loading without exposing a decorative table to keyboard users", async () => {
    renderPage();
    const loading = screen.getByRole("status", { name: "Loading..." });
    expect(loading).toHaveAttribute("aria-busy", "true");
    expect(loading.querySelectorAll("li li")).toHaveLength(0);
    expect(loading.querySelectorAll("ul > li")).toHaveLength(5);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    await screen.findByRole("list", { name: "Needs attention" });
    expect(screen.queryByRole("status", { name: "Loading..." })).not.toBeInTheDocument();
  });

  it("floats reconnect and setup fixes into Needs attention, leaving disabled plugins Installed", async () => {
    renderPage();
    const attention = await screen.findByRole("list", { name: "Needs attention" });
    expect(within(attention).getByText("Calendar")).toBeInTheDocument();
    expect(within(attention).getByText("Transit")).toBeInTheDocument();
    expect(within(attention).getByText("Reconnect")).toBeInTheDocument();
    expect(within(attention).getByText("Set up")).toBeInTheDocument();
    expect(within(attention).queryByText("Music")).not.toBeInTheDocument();
    const installed = screen.getByRole("list", { name: "Installed" });
    expect(within(installed).getByText("Disabled")).toBeInTheDocument();
    expect(within(installed).getByText("Weather")).toBeInTheDocument();
    expect(attention.compareDocumentPosition(installed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Below the rail a row leads with its state (BB-C-22, Figma 324:50158).
    expect(attention.querySelector('[data-slot="status-dot"]')?.className).toMatch(/warning/);
  });

  it("links the Set up row to the full installed detail route", async () => {
    renderPage();
    const row = await screen.findByRole("link", { name: /^Transit/ });
    expect(row).toHaveAttribute("href", "/integrations/Transit?from=installed");
    expect(within(row).getByText("Set up")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reuses the schema form in the selected desktop detail pane", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(min-width: 768px)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /^Transit/ }));
    const detail = screen.getByRole("complementary", { name: "Integration settings" });
    expect(await within(detail).findByLabelText("Stop")).toHaveValue("Central");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Weather/ }));
    expect(within(detail).getByRole("heading", { name: "Weather" })).toBeInTheDocument();
  });

  it("automatically uses compact Marketplace results on a phone", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(max-width: 767px)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    renderPage();
    await userEvent.click(await screen.findByRole("tab", { name: /Marketplace/ }));
    const title = await screen.findByText("New transit");
    expect(title.closest('[data-slot="plugin-card"]')).toHaveAttribute("data-variant", "compact");
  });

  it("shows compact PluginCard marketplace results with the install action", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /Marketplace/ }));
    await user.click(screen.getByRole("button", { name: "List view" }));
    const title = await screen.findByText("New transit");
    const card = title.closest('[data-slot="plugin-card"]');
    expect(card).toHaveAttribute("data-variant", "compact");
    expect(within(card as HTMLElement).getByRole("button", { name: "Install" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
