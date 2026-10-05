/**
 * A plugin whose users bring their own OAuth app has its Client ID field in
 * the Account connection panel's guided setup, not in the general settings
 * form, and the panel's sign-in button saves it before starting the sign-in.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";
const PLUGIN = {
  id: "music",
  name: "Music",
  category: "entertainment",
  version: "1.0.0",
  description: "Music",
  author: "FiestaBoard",
  enabled: true,
  configured: false,
  icon: "music",
  plugin_type: "data",
  config: {},
  source: {
    source_type: "registry" as const,
    repository_url: "https://github.com/example/fiestaboard-plugin--music.git",
  },
  update_available: false,
  instance_label: null,
  base_plugin_id: "music",
};

function mockInstall(userApp: boolean) {
  const events: Array<{ step: string; body?: unknown }> = [];
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins: [PLUGIN], plugin_system_enabled: true, total: 1, enabled_count: 1 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: [] })),
    http.get(`${API_BASE}/v1/plugins/music`, () =>
      HttpResponse.json({
        ...PLUGIN,
        settings_schema: {
          type: "object",
          properties: {
            client_id: { type: "string", title: "Client ID" },
            show_album: { type: "boolean", title: "Show Album", default: true },
          },
        },
        variables: {},
        max_lengths: {},
        env_vars: [],
        documentation: null,
        has_demo: false,
        demo_page_id: null,
        instances: [],
      }),
    ),
    http.get(`${API_BASE}/v1/plugins/music/data`, () =>
      HttpResponse.json({
        plugin_id: "music",
        available: false,
        data: {},
        lines: [],
        text: "",
        error: "Not signed in",
      }),
    ),
    http.patch(`${API_BASE}/v1/plugins/music`, async ({ request }) => {
      events.push({ step: "save", body: await request.json() });
      return HttpResponse.json(PLUGIN);
    }),
    http.post(`${API_BASE}/oauth/connections/music/authorize`, () => {
      events.push({ step: "authorize" });
      return HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null });
    }),
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
            configured: !userApp,
            user_app: userApp,
            shared_app: false,
            client_id_setting: userApp ? "client_id" : null,
            client_secret_setting: null,
            app_setup_url: "",
            status: "disconnected",
            scopes: [],
            expires_at: null,
            connected_at: null,
            device: null,
          },
        ],
        redirect_uri: "https://fiestaboard.app/auth/oauth/redirect",
      }),
    ),
  );
  return events;
}

async function openSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <IntegrationsPage />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.click((await screen.findAllByRole("button", { name: /configure/i }))[0]);
  await screen.findByTestId("oauth-connection");
  return user;
}

afterEach(() => vi.unstubAllGlobals());

describe("Integrations — guided setup for a plugin where users bring their own app", () => {
  it("asks for the Client ID in the connection panel only, not again in the settings form", async () => {
    mockInstall(true);
    await openSettings();
    await screen.findByTestId("oauth-setup-steps");

    const fields = await screen.findAllByLabelText("Client ID");
    expect(fields).toHaveLength(1);
    expect(within(screen.getByTestId("oauth-connection")).getByLabelText("Client ID")).toBe(fields[0]);
    // The plugin's other settings are still in the form.
    expect(screen.getByText("Show Album")).toBeInTheDocument();
  });

  it("links to the plugin's own setup guide", async () => {
    mockInstall(true);
    await openSettings();
    expect(await screen.findByRole("link", { name: "Step-by-step guide" })).toHaveAttribute(
      "href",
      "https://github.com/example/fiestaboard-plugin--music/blob/HEAD/docs/SETUP.md",
    );
  });

  it("saves the typed Client ID with the rest of the settings, then starts the sign-in", async () => {
    const events = mockInstall(true);
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    const user = await openSettings();

    await user.type(await screen.findByLabelText("Client ID"), "0123456789abcdef");
    await user.click(screen.getByRole("button", { name: "Sign in with Example Music" }));

    await waitFor(() => expect(events.map((event) => event.step)).toEqual(["save", "authorize"]));
    expect(events[0].body).toEqual({ config: { client_id: "0123456789abcdef", show_album: true } });
    // The sheet stays open: the browser is about to leave for the provider.
    expect(screen.getByTestId("oauth-connection")).toBeInTheDocument();
  });

  it("keeps a plugin that brings its own app free of any Client ID field", async () => {
    mockInstall(false);
    await openSettings();
    expect(await screen.findByRole("button", { name: "Sign in with Example Music" })).toBeEnabled();
    expect(screen.queryByTestId("oauth-setup-steps")).not.toBeInTheDocument();
    // Its (legacy) schema property is the settings form's business, as before.
    expect(screen.getAllByLabelText("Client ID")).toHaveLength(1);
    expect(within(screen.getByTestId("oauth-connection")).queryByLabelText("Client ID")).not.toBeInTheDocument();
  });
});
