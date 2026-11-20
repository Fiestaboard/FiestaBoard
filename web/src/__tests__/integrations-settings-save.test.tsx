/**
 * An installed integration's settings page at phone width (BB-C-18, C-20).
 *
 * - A value the hub rejects is marked on its own field with the hub's rule,
 *   and the failure is said beside Save rather than in a toast over it.
 * - Leaving with unsaved edits asks first.
 * - Save Changes / Saving… follow the language.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import IntegrationsLayout from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import PluginDetailPage from "../../app/routes/integrations.$pluginId";
import { server } from "./mocks/server";

const { i18nHolder } = vi.hoisted(() => ({ i18nHolder: {} as { current?: import("i18next").i18n } }));
vi.mock("@/i18n/i18next", async () => {
  const { default: i18next } = await import("i18next");
  const { initReactI18next } = await import("react-i18next");
  const { default: en } = await import("../../messages/en.json");
  const { default: de } = await import("../../messages/de.json");
  const instance = i18next.createInstance();
  await instance.use(initReactI18next).init({
    resources: { en: { translation: en }, de: { translation: de } },
    lng: "en",
    fallbackLng: "en",
    interpolation: { escapeValue: false, prefix: "{{", suffix: "}}" },
    returnNull: false,
    react: { useSuspense: false },
  });
  i18nHolder.current = instance;
  return { default: instance };
});
// The real hook, so the Save button can be read in German (BB-C-20).
vi.unmock("@/i18n/translations");
vi.unmock("react-router");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const plugin = {
  id: "random",
  name: "Random",
  category: "utility",
  version: "1.0.0",
  author: "FiestaBoard Team",
  description: "Display randomly selected values",
  enabled: true,
  configured: true,
  icon: "shuffle",
  config: {},
  source: { source_type: "builtin" },
  plugin_type: "data",
  update_available: false,
  instance_label: null,
  base_plugin_id: "random",
};
const schema = {
  type: "object",
  properties: {
    enabled: { type: "boolean", title: "Enable Random", default: true },
    choices: { type: "array", title: "Choices", items: { type: "string" }, minItems: 2, maxItems: 10 },
    refresh_seconds: { type: "integer", title: "Refresh Interval (seconds)", minimum: 60, maximum: 86400 },
  },
};

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        path: "/integrations",
        Component: IntegrationsLayout,
        children: [
          { index: true, Component: IntegrationsPage },
          { path: ":pluginId", Component: PluginDetailPage },
        ],
      },
    ],
    { initialEntries: ["/integrations", path], initialIndex: 1 },
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
  server.use(
    http.get("/api/plugins", () =>
      HttpResponse.json({ plugins: [plugin], total: 1, enabled_count: 1, plugin_system_enabled: true }),
    ),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [] })),
    http.get("/api/oauth/connections", () => HttpResponse.json({ connections: [], redirect_uri: "" })),
    http.get("/api/v1/plugins/random", () =>
      HttpResponse.json({
        ...plugin,
        config: { enabled: true, choices: ["TACOS", "PIZZA"], refresh_seconds: 300 },
        settings_schema: schema,
        variables: {},
        env_vars: [],
        has_demo: false,
      }),
    ),
    http.get("/api/v1/plugins/random/data", () => HttpResponse.json({ available: true, data: {} })),
    http.patch("/api/v1/plugins/random", () =>
      HttpResponse.json(
        {
          detail: {
            message: "Configuration for 'random' failed validation.",
            errors: ["Refresh interval must be at least 60 seconds", "Refresh interval must be at least 60 seconds"],
          },
        },
        { status: 400 },
      ),
    ),
  );
});

afterEach(async () => {
  await act(async () => {
    await i18nHolder.current!.changeLanguage("en");
  });
});

describe("Integration settings: saving", () => {
  it("marks the rejected field with the hub's rule, beside Save and not in a toast", async () => {
    const user = userEvent.setup();
    renderAt("/integrations/random?from=installed");
    const interval = await screen.findByRole("spinbutton", { name: "Refresh Interval (seconds)" });
    await user.clear(interval);
    await user.type(interval, "-5");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(interval).toHaveAttribute("aria-invalid", "true"));
    expect(interval).toHaveAccessibleDescription("Refresh interval must be at least 60 seconds");
    expect(screen.getByRole("alert")).toHaveTextContent(/check the highlighted settings/i);
    expect(toast.error).not.toHaveBeenCalled();
    await waitFor(() => expect(interval).toHaveFocus());

    // Editing the refused field clears its message and the alert.
    await user.type(interval, "0");
    expect(interval).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("asks before leaving with unsaved edits, and keeps them on Keep editing", async () => {
    const user = userEvent.setup();
    const router = renderAt("/integrations/random?from=installed");
    const first = await screen.findByRole("textbox", { name: "Choices 1" });
    await user.type(first, "S");
    await act(async () => {
      await router.navigate("/integrations?tab=installed");
    });
    expect(await screen.findByRole("alertdialog", { name: "Discard unsaved changes?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(router.state.location.pathname).toBe("/integrations/random");
    expect(screen.getByRole("textbox", { name: "Choices 1" })).toHaveValue("TACOSS");

    await act(async () => {
      await router.navigate("/integrations?tab=installed");
    });
    await user.click(await screen.findByRole("button", { name: "Discard and leave" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/integrations"));
  });

  it("goes back to the list without asking once the edits are saved", async () => {
    server.use(http.patch("/api/v1/plugins/random", () => HttpResponse.json({ ...plugin })));
    const user = userEvent.setup();
    const router = renderAt("/integrations/random?from=installed");
    await user.type(await screen.findByRole("textbox", { name: "Choices 1" }), "S");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/integrations"));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("leaves without asking when nothing changed", async () => {
    const router = renderAt("/integrations/random?from=installed");
    await screen.findByRole("textbox", { name: "Choices 1" });
    await act(async () => {
      await router.navigate("/integrations?tab=installed");
    });
    await waitFor(() => expect(router.state.location.pathname).toBe("/integrations"));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("lets a guided sign-in leave for the provider without a Leave site? prompt", async () => {
    // A plugin whose users bring their own OAuth app: the Client ID is typed in
    // the Account panel, and Sign in saves it before leaving for the provider.
    const music = { ...plugin, id: "music", name: "Music", base_plugin_id: "music", configured: false };
    let detailReads = 0;
    server.use(
      http.get("/api/plugins", () =>
        HttpResponse.json({ plugins: [music], total: 1, enabled_count: 1, plugin_system_enabled: true }),
      ),
      http.get("/api/v1/plugins/music", async () => {
        // The post-save refetch is slow, so nothing but the save itself can
        // clear the unsaved state before the browser leaves.
        if (detailReads++ > 0) await delay(2000);
        return HttpResponse.json({
          ...music,
          config: {},
          settings_schema: { type: "object", properties: { client_id: { type: "string", title: "Client ID" } } },
          variables: {},
          env_vars: [],
          has_demo: false,
        });
      }),
      http.get("/api/v1/plugins/music/data", () => HttpResponse.json({ available: false, data: {} })),
      http.patch("/api/v1/plugins/music", () => HttpResponse.json(music)),
      http.post("/api/oauth/connections/music/authorize", () =>
        HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null }),
      ),
      http.get("/api/oauth/connections", () =>
        HttpResponse.json({
          connections: [
            {
              id: "music",
              plugin_id: "music",
              instance_label: null,
              plugin_name: "Music",
              provider_name: "Example Music",
              flows: ["relay"],
              configured: false,
              user_app: true,
              shared_app: false,
              client_id_setting: "client_id",
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
    const prompted: boolean[] = [];
    vi.stubGlobal("location", {
      ...window.location,
      origin: window.location.origin,
      assign: vi.fn(() => {
        const leaving = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(leaving);
        prompted.push(leaving.defaultPrevented);
      }),
    });
    const user = userEvent.setup();
    renderAt("/integrations/music?from=installed");
    await user.type(await screen.findByLabelText("Client ID"), "0123456789abcdef");
    await user.click(screen.getByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() => expect(prompted).toEqual([false]));
    vi.unstubAllGlobals();
  });

  it("says Save Changes in the reader's language", async () => {
    await act(async () => {
      await i18nHolder.current!.changeLanguage("de");
    });
    renderAt("/integrations/random?from=installed");
    expect(await screen.findByRole("button", { name: "Änderungen speichern" })).toBeInTheDocument();
  });
});
