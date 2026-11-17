import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsSection } from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import PluginDetailPage from "../../app/routes/integrations.$pluginId";
import { server } from "./mocks/server";

const navigation = vi.hoisted(() => ({
  pluginId: "calendar",
  desktop: false,
  push: vi.fn(),
  replace: vi.fn(),
  assign: vi.fn(),
}));
vi.mock("@/hooks/use-router", async (original) => ({
  ...(await original<typeof import("@/hooks/use-router")>()),
  useParams: () => ({ pluginId: navigation.pluginId || undefined }),
  useSearchParams: () => new URLSearchParams("from=installed"),
  useRouter: () => ({ push: navigation.push, replace: navigation.replace, back: vi.fn() }),
}));
vi.mock("@/hooks/use-media-query", () => ({
  useMediaQuery: (query: string) => (query === "(min-width: 768px)" ? navigation.desktop : !navigation.desktop),
}));
const plugin = {
  id: "calendar",
  name: "Calendar",
  category: "utility",
  version: "2.3.0",
  author: "Example author",
  description: "Calendar events",
  enabled: true,
  configured: true,
  icon: "calendar",
  config: {},
  source: { source_type: "registry", repository_url: "https://github.com/example/calendar" },
  plugin_type: "data",
  update_available: false,
  instance_label: null,
  base_plugin_id: "calendar",
};
function renderView(child: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {child}
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  navigation.pluginId = "calendar";
  navigation.desktop = false;
  navigation.push.mockClear();
  navigation.replace.mockClear();
  navigation.assign.mockClear();
  server.use(
    http.get("/api/plugins", () =>
      HttpResponse.json({ plugins: [plugin], total: 1, enabled_count: 1, plugin_system_enabled: true }),
    ),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [] })),
    http.get("/api/v1/plugins/calendar", () =>
      HttpResponse.json({
        ...plugin,
        config: { stop: "Central", api_key: "***" },
        settings_schema: {
          type: "object",
          properties: {
            stop: { type: "string", title: "Stop" },
            api_key: { type: "string", title: "API key", secret: true },
          },
        },
        variables: { simple: { next_title: { description: "Next event", max_length: 40 } } },
        env_vars: [],
        has_demo: false,
        documentation: "# Calendar guide\n\nRead [setup](docs/SETUP.md).\n\n![Preview](docs/board.png)",
      }),
    ),
    http.get("/api/v1/plugins/calendar/data", () =>
      HttpResponse.json({ available: true, data: { next_title: "Team meeting" } }),
    ),
    http.get("/api/oauth/connections", () =>
      HttpResponse.json({
        connections: [
          {
            id: "calendar",
            plugin_id: "calendar",
            plugin_name: "Calendar",
            provider_name: "Example Calendar",
            status: "reauthorization_required",
            status_reason: "refresh_refused",
            configured: true,
            flows: ["relay"],
            shared_app: true,
            user_app: false,
            scopes: [],
            expires_at: null,
            connected_at: null,
            device: null,
          },
        ],
        redirect_uri: "https://example.com/return",
      }),
    ),
    http.get("https://raw.githubusercontent.com/example/calendar/main/README.md", () =>
      HttpResponse.text("# Calendar guide\n\nRead [setup](docs/SETUP.md).\n\n![Preview](docs/board.png)"),
    ),
  );
});

describe("Integrations review: supported detail flows", () => {
  it("opens installed detail absent from registry with Back and a factual reconnect consequence", async () => {
    renderView(
      <IntegrationsSection>
        <PluginDetailPage />
      </IntegrationsSection>,
    );
    expect(await screen.findByRole("link", { name: "Back to Integrations" })).toHaveAttribute(
      "href",
      "/integrations?tab=installed",
    );
    expect(await screen.findByText("Reconnect Calendar")).toBeInTheDocument();
    expect(
      screen.getByText(/Data for pages using this integration may be unavailable or out of date until you reconnect/),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Reconnect" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Stop")).toHaveValue("Central");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Breadcrumb" }).querySelector("a")).toHaveAttribute(
      "href",
      "/integrations?tab=installed",
    );
  });

  it("offers Settings Variables README, renders live variables and kit Prose with rewritten links and About metadata", async () => {
    renderView(<PluginDetailPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Variables" }));
    expect(await screen.findByText("Team meeting")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "README" }));
    const heading = await screen.findByRole("heading", { name: "Calendar guide" });
    expect(heading.closest('[data-slot="prose"]')).not.toBeNull();
    expect(screen.getByRole("link", { name: "setup" })).toHaveAttribute(
      "href",
      "https://github.com/example/calendar/blob/main/docs/SETUP.md",
    );
    expect(screen.getByAltText("Preview")).toHaveAttribute(
      "src",
      "https://raw.githubusercontent.com/example/calendar/main/docs/board.png",
    );
    const about = screen.getByRole("region", { name: "About" });
    expect(within(about).getByText("2.3.0")).toBeInTheDocument();
    expect(within(about).getByText("Example author")).toBeInTheDocument();
    expect(within(about).getByRole("link", { name: /example\/calendar/ })).toHaveAttribute(
      "href",
      "https://github.com/example/calendar",
    );
    await user.click(screen.getByRole("tab", { name: "Settings" }));
    expect(screen.getByLabelText("Stop")).toHaveValue("Central");
  });

  it("refreshes the selected schema after updating an integration from its detail header", async () => {
    let updated = false;
    server.use(
      http.get("/api/plugins", () =>
        HttpResponse.json({
          plugins: [{ ...plugin, update_available: !updated }],
          total: 1,
          enabled_count: 1,
          plugin_system_enabled: true,
        }),
      ),
      http.get("/api/v1/plugins/calendar", () =>
        HttpResponse.json({
          ...plugin,
          settings_schema: {
            type: "object",
            properties: { stop: { type: "string", title: updated ? "Updated stop" : "Stop" } },
          },
          config: { stop: "Central" },
          variables: {},
          env_vars: [],
        }),
      ),
      http.post("/api/plugins/calendar/update", () => {
        updated = true;
        return HttpResponse.json({ plugin_id: "calendar", message: "Updated" });
      }),
    );
    renderView(<PluginDetailPage />);
    await screen.findByLabelText("Stop");
    await userEvent.click(screen.getByRole("button", { name: "More options" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Update" }));
    expect(await screen.findByLabelText("Updated stop")).toHaveValue("Central");
  });

  it("opens the full README route from the selected desktop detail", async () => {
    navigation.pluginId = "";
    navigation.desktop = true;
    renderView(<IntegrationsPage />);
    await userEvent.click(await screen.findByRole("tab", { name: "README" }));
    expect(navigation.push).toHaveBeenCalledWith("/integrations/calendar?from=installed&tab=readme");
  });

  it.each(["leading", "description", "trailing"])(
    "makes the whole phone row target operable from its %s area",
    async (slot) => {
      navigation.pluginId = "";
      renderView(<IntegrationsPage />);
      const row = (await screen.findByText("Calendar")).closest('[data-slot="list-row"]')!;
      expect(row.tagName).toBe("A");
      expect(row).toHaveAttribute("href", "/integrations/calendar?from=installed");
      expect(row.querySelectorAll('button,input,[role="switch"],a')).toHaveLength(0);
      const area = row.querySelector(`[data-slot="list-row-${slot}"]`)!;
      expect(area.closest("a")).toBe(row);
      expect(area).toBeInTheDocument();
    },
  );

  it.each(["leading", "description", "trailing"])(
    "opens the selected desktop detail when its %s area is activated",
    async (slot) => {
      navigation.pluginId = "";
      navigation.desktop = true;
      renderView(<IntegrationsPage />);
      const row = await screen.findByRole("button", { name: /^Calendar/ });
      const detail = screen.getByRole("complementary", { name: "Integration settings" });
      await userEvent.click(await within(detail).findByRole("button", { name: "Cancel" }));
      expect(within(detail).queryByRole("heading", { name: "Calendar" })).not.toBeInTheDocument();
      await userEvent.click(row.querySelector(`[data-slot="list-row-${slot}"]`)!);
      expect(await within(detail).findByRole("heading", { name: "Calendar" })).toBeInTheDocument();
    },
  );

  it("keeps lifecycle controls outside the row primary target and changing enable state does not navigate", async () => {
    navigation.pluginId = "";
    navigation.desktop = true;
    const writes: unknown[] = [];
    server.use(
      http.patch("/api/v1/plugins/calendar", async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json(plugin);
      }),
    );
    renderView(<IntegrationsPage />);
    const row = await screen.findByRole("button", { name: /^Calendar/ });
    expect(row.tagName).toBe("BUTTON");
    expect(row.querySelectorAll('button,input,[role="switch"],a')).toHaveLength(0);
    const detail = screen.getByRole("complementary", { name: "Integration settings" });
    await userEvent.click(await within(detail).findByRole("switch", { name: "Toggle Calendar" }));
    await waitFor(() => expect(writes).toEqual([{ enabled: false }]));
    expect(navigation.push).not.toHaveBeenCalled();
    expect(await within(detail).findByRole("tab", { name: "Settings" })).toBeInTheDocument();
  });
});
