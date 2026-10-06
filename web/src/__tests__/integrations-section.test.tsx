/**
 * Integrations is a section: its header holds still while a plugin's page
 * opens beneath it under "Integrations › <plugin>", and the crumb goes back to
 * the Marketplace tab the plugin was opened from.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsSection } from "../../app/routes/integrations";
import PluginDetailPage from "../../app/routes/integrations.$pluginId";
import { server } from "./mocks/server";

const API_BASE = "/api";
const params: { pluginId?: string } = {};

vi.mock("@/hooks/use-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/use-router")>()),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  useParams: () => params,
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function mockRegistry({ installed = false } = {}) {
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () =>
      HttpResponse.json({
        entries: [
          {
            id: "weather",
            name: "Weather",
            description: "Current conditions on your board",
            category: "weather",
            repository: "https://example.com/weather",
            branch: "main",
            author: "FiestaBoard",
            fiestaboard_version: ">=8.0.0",
            icon: "puzzle",
            installed,
          },
        ],
      }),
    ),
  );
}

function renderSection(child: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <IntegrationsSection>{child}</IntegrationsSection>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  delete params.pluginId;
});

describe("/integrations section", () => {
  it("offers Check for updates on the section header at the list", () => {
    mockRegistry();
    renderSection(<p>list</p>);
    expect(screen.getByRole("heading", { level: 1, name: "Integrations" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /check for updates/i }).closest("[inert]")).toBeNull();
  });

  it("names the open plugin under a breadcrumb back to the Marketplace", async () => {
    mockRegistry();
    params.pluginId = "weather";
    renderSection(<PluginDetailPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Integrations" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "Weather" })).toBeInTheDocument();
    const trail = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(trail).getByRole("link", { name: "Integrations" })).toHaveAttribute(
      "href",
      "/integrations?tab=marketplace",
    );
  });

  it("drops the old Back to Marketplace link and the page's own h1", async () => {
    mockRegistry();
    params.pluginId = "weather";
    renderSection(<PluginDetailPage />);
    await screen.findByRole("heading", { level: 2, name: "Weather" });
    expect(screen.queryByRole("link", { name: /back to marketplace/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("puts Install on the sub-header row beside the plugin's name", async () => {
    mockRegistry();
    params.pluginId = "weather";
    renderSection(<PluginDetailPage />);
    const subheader = document.querySelector<HTMLElement>("[data-slot=page-subheader]")!;
    expect(await within(subheader).findByRole("button", { name: /install/i })).toBeInTheDocument();
  });
});
