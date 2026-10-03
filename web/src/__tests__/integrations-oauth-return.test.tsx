/**
 * An OAuth sign-in ends with the board redirecting the browser to
 * `/integrations?tab=installed&oauth=...&plugin=...` (src/oauth/routes.py).
 * The page has to say what happened, put the person back in the plugin they
 * were connecting, and clean the URL so a reload does not say it again.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: navigation.replace, back: vi.fn(), forward: vi.fn() }),
  useSearchParams: () => new URLSearchParams(navigation.search),
  usePathname: () => "/integrations",
  useParams: () => ({}),
}));

function plugin(id: string, name: string) {
  return {
    id,
    name,
    category: "entertainment",
    version: "1.0.0",
    description: name,
    author: "FiestaBoard",
    enabled: true,
    configured: true,
    icon: "music",
    plugin_type: "data",
    config: {},
    source: { source_type: "builtin" as const },
    update_available: false,
    instance_label: null,
    base_plugin_id: id,
  };
}

function mockInstall() {
  const plugins = [plugin("music", "Music"), plugin("weather", "Weather")];
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins, plugin_system_enabled: true, total: 2, enabled_count: 2 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: [] })),
    http.get(`${API_BASE}/v1/plugins/:id`, ({ params }) =>
      HttpResponse.json({
        ...plugins.find((p) => p.id === params.id),
        settings_schema: { type: "object", properties: {} },
        variables: {},
        max_lengths: {},
        env_vars: [],
        documentation: null,
        has_demo: false,
        demo_page_id: null,
        instances: [],
      }),
    ),
    http.get(`${API_BASE}/v1/plugins/:id/data`, ({ params }) =>
      HttpResponse.json({ plugin_id: params.id, available: true, data: {}, lines: [], text: "", error: null }),
    ),
    http.get(`${API_BASE}/oauth/connections`, () =>
      HttpResponse.json({
        connections: [
          {
            id: "music",
            plugin_id: "music",
            instance_label: null,
            plugin_name: "Music",
            provider_name: "Example Music",
            flows: ["relay"],
            configured: true,
            status: "connected",
            scopes: [],
            expires_at: null,
            connected_at: 1_800_000_000,
            device: null,
          },
        ],
        redirect_uri: "https://fiestaboard.app/auth/oauth/redirect.html",
      }),
    ),
  );
}

function renderPage(search: string) {
  navigation.search = search;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <IntegrationsPage />
    </QueryClientProvider>,
  );
}

describe("Integrations — returning from an OAuth sign-in", () => {
  beforeEach(() => {
    navigation.replace.mockClear();
    vi.restoreAllMocks();
    mockInstall();
  });

  it("confirms a successful connection and reopens that plugin's settings", async () => {
    const success = vi.spyOn(toast, "success");
    renderPage("tab=installed&oauth=connected&plugin=music");

    await waitFor(() => expect(success).toHaveBeenCalledWith("Account connected."));
    // The sheet opened by itself, on the plugin that was being connected.
    expect(await screen.findByTestId("oauth-connection")).toHaveTextContent(
      "This plugin is signed in to Example Music.",
    );
  });

  it("cleans the outcome out of the URL so a reload does not report it again", async () => {
    renderPage("tab=installed&oauth=connected&plugin=music");
    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith("/integrations?tab=installed", { scroll: false }),
    );
  });

  it("explains a failed sign-in in words, not with its reason code", async () => {
    const error = vi.spyOn(toast, "error");
    renderPage("tab=installed&oauth=error&plugin=music&reason=access_denied");
    await waitFor(() => expect(error).toHaveBeenCalledWith("The sign-in was declined, so nothing was connected."));
  });

  it("reports a failure that names no plugin without opening any settings", async () => {
    const error = vi.spyOn(toast, "error");
    renderPage("tab=installed&oauth=error&reason=invalid_state");
    await waitFor(() => expect(error).toHaveBeenCalledTimes(1));
    await screen.findAllByRole("button", { name: /configure/i });
    expect(screen.queryByTestId("oauth-connection")).not.toBeInTheDocument();
  });

  it("does nothing on an ordinary visit", async () => {
    const success = vi.spyOn(toast, "success");
    const error = vi.spyOn(toast, "error");
    renderPage("tab=installed");
    await screen.findAllByRole("button", { name: /configure/i });
    expect(success).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(screen.queryByTestId("oauth-connection")).not.toBeInTheDocument();
  });
});
