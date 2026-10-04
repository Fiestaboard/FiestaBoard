/**
 * The "Account connection" section of a plugin's settings sheet, and the
 * helpers that read an OAuth sign-in's outcome off the URL it returns to.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  OAuthConnectionPanel,
  OAuthConnectionSection,
  oauthReturnErrorKey,
  readOAuthReturn,
} from "@/components/plugin-settings";
import { boardAddress, type OAuthConnection } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";
const REDIRECT_URI = "https://fiestaboard.app/auth/oauth/redirect";

const RELAY: OAuthConnection = {
  id: "music",
  plugin_id: "music",
  instance_label: null,
  plugin_name: "Music",
  provider_name: "Example Music",
  flows: ["relay"],
  configured: true,
  user_app: true,
  shared_app: false,
  client_id_setting: "client_id",
  client_secret_setting: null,
  app_setup_url: "",
  status: "disconnected",
  scopes: ["read-playing"],
  expires_at: null,
  connected_at: null,
  device: null,
};

const DEVICE: OAuthConnection = {
  ...RELAY,
  id: "git",
  plugin_id: "git",
  provider_name: "Example Git",
  flows: ["device"],
};

const PENDING_DEVICE = {
  status: "pending" as const,
  user_code: "WDJB-MJHT",
  verification_uri: "https://example.com/device",
  verification_uri_complete: "https://example.com/device?user_code=WDJB-MJHT",
  expires_at: 1_900_000_000,
  detail: "",
};

function serveConnections(...connections: OAuthConnection[]) {
  server.use(
    http.get(`${API_BASE}/oauth/connections`, () => HttpResponse.json({ connections, redirect_uri: REDIRECT_URI })),
  );
}

interface HarnessOptions {
  /** The settings sheet's form values. "***" is how a saved Client ID arrives from the API. */
  values?: Record<string, unknown>;
  save?: () => Promise<void>;
  setupGuideUrl?: string;
}

/** Stands in for the settings sheet, which owns the form values. */
function Harness({ pluginId, values: initial, save, setupGuideUrl }: HarnessOptions & { pluginId: string }) {
  const [values, setValues] = useState<Record<string, unknown>>(initial ?? { client_id: "***" });
  return (
    <OAuthConnectionSection
      pluginId={pluginId}
      appFields={{
        values,
        onChange: (key, value) => setValues((current) => ({ ...current, [key]: value })),
        save: save ?? (async () => {}),
        setupGuideUrl,
      }}
    />
  );
}

function renderSection(pluginId: string, options: HarnessOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Harness pluginId={pluginId} {...options} />
    </QueryClientProvider>,
  );
}

type WindowWithRouterContext = Window & { __reactRouterContext?: { basename?: string } };

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  delete (window as WindowWithRouterContext).__reactRouterContext;
});

describe("OAuthConnectionSection", () => {
  it("renders nothing for a plugin that does not sign in with OAuth", async () => {
    let asked = false;
    server.use(
      http.get(`${API_BASE}/oauth/connections`, () => {
        asked = true;
        return HttpResponse.json({ connections: [RELAY], redirect_uri: REDIRECT_URI });
      }),
    );
    renderSection("weather");
    await waitFor(() => expect(asked).toBe(true));
    expect(screen.queryByTestId("oauth-connection")).not.toBeInTheDocument();
  });

  it("offers to connect a plugin that is not connected yet", async () => {
    serveConnections(RELAY);
    renderSection("music");
    expect(await screen.findByRole("button", { name: "Sign in with Example Music" })).toBeEnabled();
    // The status line is a live region, so a change is announced, not just recoloured.
    expect(screen.getByText("Not connected")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
  });

  it("will not sign in until there is a Client ID, and says why", async () => {
    serveConnections({ ...RELAY, configured: false });
    renderSection("music", { values: {} });
    const connect = await screen.findByRole("button", { name: "Sign in with Example Music" });
    expect(connect).toBeDisabled();
    expect(connect).toHaveAccessibleDescription("Paste the Client ID above to sign in.");
  });

  it("walks someone with no app yet through creating one, in order", async () => {
    serveConnections({ ...RELAY, configured: false, app_setup_url: "https://example.com/developers" });
    renderSection("music", { values: {}, setupGuideUrl: "https://github.com/example/plugin/blob/HEAD/docs/SETUP.md" });

    const steps = within(await screen.findByTestId("oauth-setup-steps")).getAllByRole("listitem");
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("Create an app with Example Music");
    expect(steps[1]).toHaveTextContent("Give the app this redirect URI");
    expect(steps[1]).toHaveTextContent(REDIRECT_URI);
    expect(steps[2]).toHaveTextContent("Copy the app's details here");
    expect(within(steps[2]).getByLabelText("Client ID")).toHaveValue("");
    expect(screen.getByText(/asks everyone to sign in through an app of their own/)).toBeInTheDocument();

    const developerPage = within(steps[0]).getByRole("link", { name: "Open Example Music's developer page" });
    expect(developerPage).toHaveAttribute("href", "https://example.com/developers");
    expect(developerPage).toHaveAttribute("target", "_blank");
    expect(developerPage).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(steps[0]).getByRole("link", { name: "Step-by-step guide" })).toHaveAttribute(
      "href",
      "https://github.com/example/plugin/blob/HEAD/docs/SETUP.md",
    );
  });

  it("offers no links it was not given", async () => {
    serveConnections({ ...RELAY, configured: false });
    renderSection("music", { values: {} });
    const steps = within(await screen.findByTestId("oauth-setup-steps")).getAllByRole("listitem");
    expect(within(steps[0]).queryByRole("link")).not.toBeInTheDocument();
  });

  it("saves a Client ID that was just typed, then starts the sign-in, with one press", async () => {
    serveConnections({ ...RELAY, configured: false });
    const order: string[] = [];
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/authorize`, () => {
        order.push("authorize");
        return HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null });
      }),
    );
    const user = userEvent.setup();
    renderSection("music", {
      values: {},
      save: async () => {
        order.push("save");
      },
    });

    await user.type(await screen.findByLabelText("Client ID"), "0123456789abcdef");
    const connect = screen.getByRole("button", { name: "Sign in with Example Music" });
    expect(connect).toBeEnabled();
    await user.click(connect);

    await waitFor(() => expect(order).toEqual(["save", "authorize"]));
  });

  it("does not start the sign-in when the settings cannot be saved", async () => {
    serveConnections({ ...RELAY, configured: false });
    let authorized = false;
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/authorize`, () => {
        authorized = true;
        return HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null });
      }),
    );
    const { toast } = await import("sonner");
    const errorToast = vi.spyOn(toast, "error");
    renderSection("music", {
      values: { client_id: "not-a-real-id" },
      save: async () => {
        throw new Error("Client ID should be 32 characters");
      },
    });

    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));

    await waitFor(() =>
      expect(errorToast).toHaveBeenCalledWith("Could not save the settings: Client ID should be 32 characters"),
    );
    expect(authorized).toBe(false);
  });

  it("asks for the client secret too when the plugin needs one", async () => {
    serveConnections({ ...RELAY, configured: false, client_secret_setting: "client_secret" });
    renderSection("music", { values: {} });
    expect(await screen.findByLabelText("Client secret")).toHaveAttribute("type", "password");
  });

  it("leaves out the redirect step for a device-flow plugin", async () => {
    serveConnections({ ...DEVICE, configured: false });
    renderSection("git", { values: {} });
    const steps = within(await screen.findByTestId("oauth-setup-steps")).getAllByRole("listitem");
    expect(steps).toHaveLength(2);
    expect(steps[1]).toHaveTextContent("Copy the app's details here");
  });

  it("puts the setup away once connected", async () => {
    serveConnections({ ...RELAY, status: "connected" });
    renderSection("music");
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.queryByTestId("oauth-setup-steps")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Client ID")).not.toBeInTheDocument();
  });

  it("shows the redirect URI to register with the provider", async () => {
    serveConnections(RELAY);
    renderSection("music");
    expect(await screen.findByText(REDIRECT_URI)).toBeInTheDocument();
    expect(screen.getByText("Give the app this redirect URI")).toBeInTheDocument();
  });

  it("copies the redirect URI, since it is typed into another site", async () => {
    serveConnections(RELAY);
    const user = userEvent.setup();
    renderSection("music");
    await user.click(await screen.findByRole("button", { name: "Copy redirect URI" }));
    expect(await navigator.clipboard.readText()).toBe(REDIRECT_URI);
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("says what to expect on the way back from the provider", async () => {
    serveConnections(RELAY);
    renderSection("music");
    expect(await screen.findByText(/asks you to confirm it/)).toBeInTheDocument();
  });

  it("asks for no setup when the plugin brings its own app", async () => {
    serveConnections({ ...RELAY, user_app: false, client_id_setting: null });
    renderSection("music", { values: {} });
    expect(await screen.findByRole("button", { name: "Sign in with Example Music" })).toBeEnabled();
    expect(screen.queryByTestId("oauth-setup-steps")).not.toBeInTheDocument();
    expect(screen.queryByText(REDIRECT_URI)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Client ID")).not.toBeInTheDocument();
    // What the trip back looks like still matters to anyone about to make it.
    expect(screen.getByText(/asks you to confirm it/)).toBeInTheDocument();
  });

  it("leads with a plain sign-in when the plugin ships an app the user may swap out", async () => {
    serveConnections({ ...RELAY, shared_app: true, app_setup_url: "https://example.com/developers" });
    renderSection("music", { values: {} });
    expect(await screen.findByRole("button", { name: "Sign in with Example Music" })).toBeEnabled();
    expect(screen.queryByText(/asks everyone to sign in through an app of their own/)).not.toBeInTheDocument();
    expect(screen.queryByText("Paste the Client ID above to sign in.")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Use your own app (optional)" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("Client ID")).not.toBeInTheDocument();
    expect(screen.queryByTestId("oauth-setup-steps")).not.toBeInTheDocument();
  });

  it("signs in with the shipped app without saving when no own app was entered", async () => {
    serveConnections({ ...RELAY, shared_app: true });
    const order: string[] = [];
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/authorize`, () => {
        order.push("authorize");
        return HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null });
      }),
    );
    const user = userEvent.setup();
    renderSection("music", { values: {}, save: async () => void order.push("save") });
    await user.click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() => expect(order).toEqual(["authorize"]));
  });

  it("keeps the own-app setup behind the optional section, and saves an ID typed there first", async () => {
    serveConnections({ ...RELAY, shared_app: true, app_setup_url: "https://example.com/developers" });
    const order: string[] = [];
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/authorize`, () => {
        order.push("authorize");
        return HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null });
      }),
    );
    const user = userEvent.setup();
    renderSection("music", { values: {}, save: async () => void order.push("save") });

    const toggle = await screen.findByRole("button", { name: "Use your own app (optional)" });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const steps = within(screen.getByTestId("oauth-setup-steps")).getAllByRole("listitem");
    expect(within(steps[0]).getByRole("link", { name: "Open Example Music's developer page" })).toHaveAttribute(
      "href",
      "https://example.com/developers",
    );
    expect(screen.getByText(REDIRECT_URI)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Client ID"), "my-own-app");
    await user.click(screen.getByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() => expect(order).toEqual(["save", "authorize"]));
  });

  it("opens the own-app section when the user already saved an app of their own", async () => {
    serveConnections({ ...RELAY, shared_app: true });
    renderSection("music");
    expect(await screen.findByRole("button", { name: "Use your own app (optional)" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByLabelText("Client ID")).toHaveValue("***");
  });

  it("keeps the guided setup in front for a plugin that ships no app", async () => {
    serveConnections({ ...RELAY, configured: false });
    renderSection("music", { values: {} });
    expect(await screen.findByTestId("oauth-setup-steps")).toBeInTheDocument();
    expect(screen.getByLabelText("Client ID")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use your own app (optional)" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in with Example Music" })).toBeDisabled();
  });

  it("does not mention the relay for a device-flow plugin", async () => {
    serveConnections(DEVICE);
    renderSection("git");
    await screen.findByRole("button", { name: "Sign in with Example Git" });
    expect(screen.queryByText(REDIRECT_URI)).not.toBeInTheDocument();
    expect(screen.queryByText(/asks you to confirm it/)).not.toBeInTheDocument();
  });

  it("sends the browser to the provider when a relay connection starts", async () => {
    serveConnections(RELAY);
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign });
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/authorize`, () =>
        HttpResponse.json({
          flow: "relay",
          authorization_url: "https://accounts.example.com/authorize?state=abc",
          device: null,
        }),
      ),
    );
    renderSection("music");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.example.com/authorize?state=abc"));
  });

  it("tells the board which address it is being browsed at, so the sign-in can come back", async () => {
    serveConnections(RELAY);
    vi.stubGlobal("location", { ...window.location, origin: "http://192.168.1.50:4420", assign: vi.fn() });
    const bodies: unknown[] = [];
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/authorize`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null });
      }),
    );
    renderSection("music");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() => expect(bodies).toEqual([{ board_url: "http://192.168.1.50:4420" }]));
  });

  it("shows the code to type when a device connection starts", async () => {
    let started = false;
    server.use(
      http.get(`${API_BASE}/oauth/connections`, () =>
        HttpResponse.json({
          connections: [{ ...DEVICE, device: started ? PENDING_DEVICE : null }],
          redirect_uri: REDIRECT_URI,
        }),
      ),
      http.post(`${API_BASE}/oauth/connections/git/authorize`, () => {
        started = true;
        return HttpResponse.json({ flow: "device", authorization_url: "", device: PENDING_DEVICE });
      }),
    );
    renderSection("git");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Git" }));

    expect(await screen.findByTestId("oauth-user-code")).toHaveTextContent("WDJB-MJHT");
    expect(screen.getByText("Waiting for approval")).toHaveAttribute("role", "status");
    // The code on screen is the thing to act on; the button now only replaces it.
    expect(screen.getByRole("button", { name: "Get a new code" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in with Example Git" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "https://example.com/device" });
    expect(link).toHaveAttribute("href", "https://example.com/device?user_code=WDJB-MJHT");
  });

  it("copies the device code for typing on the other device", async () => {
    serveConnections({ ...DEVICE, device: PENDING_DEVICE });
    const user = userEvent.setup();
    renderSection("git");
    await user.click(await screen.findByRole("button", { name: "Copy code" }));
    expect(await navigator.clipboard.readText()).toBe("WDJB-MJHT");
  });

  it.each([
    ["expired", /That code expired before it was approved/],
    ["denied", /The sign-in was declined/],
    ["failed", /could not be completed \(invalid_client\)/],
  ] as const)("explains a device sign-in that ended as %s", async (status, message) => {
    serveConnections({ ...DEVICE, device: { ...PENDING_DEVICE, status, detail: "invalid_client" } });
    renderSection("git");
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByTestId("oauth-user-code")).not.toBeInTheDocument();
  });

  it("reports a connection that could not start", async () => {
    serveConnections(RELAY);
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/authorize`, () =>
        HttpResponse.json({ detail: "Music needs a client ID before it can connect." }, { status: 400 }),
      ),
    );
    const { toast } = await import("sonner");
    const errorToast = vi.spyOn(toast, "error");
    renderSection("music");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() =>
      expect(errorToast).toHaveBeenCalledWith(
        "Could not start the connection: Music needs a client ID before it can connect.",
      ),
    );
  });

  it("offers to disconnect a connected plugin, and does it", async () => {
    let connected = true;
    let deletes = 0;
    server.use(
      http.get(`${API_BASE}/oauth/connections`, () =>
        HttpResponse.json({
          connections: [{ ...RELAY, status: connected ? "connected" : "disconnected" }],
          redirect_uri: REDIRECT_URI,
        }),
      ),
      http.delete(`${API_BASE}/oauth/connections/music`, () => {
        deletes += 1;
        connected = false;
        return HttpResponse.json({ ...RELAY, status: "disconnected" });
      }),
    );
    renderSection("music");
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeInTheDocument();
    // Setup-time hints are gone once the connection exists.
    expect(screen.queryByText(REDIRECT_URI)).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Disconnect" }));

    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(deletes).toBe(1);
  });

  it("asks for a reconnect when the provider stopped accepting the connection", async () => {
    serveConnections({ ...RELAY, status: "reauthorization_required" });
    renderSection("music");
    expect(await screen.findByText("Reconnect needed")).toBeInTheDocument();
    expect(screen.getByText(/Example Music stopped accepting this connection/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeEnabled();
  });

  it("addresses a named instance by its own key", async () => {
    serveConnections({ ...RELAY, id: "music:kitchen", instance_label: "kitchen" });
    const requested: string[] = [];
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    server.use(
      http.post(`${API_BASE}/oauth/connections/:id/authorize`, ({ params }) => {
        requested.push(String(params.id));
        return HttpResponse.json({ flow: "relay", authorization_url: "https://accounts.example.com/a", device: null });
      }),
    );
    renderSection("music:kitchen");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() => expect(requested).toEqual(["music:kitchen"]));
  });
});

describe("finishing a sign-in by pasting what the provider showed", () => {
  const PASTE_TOGGLE = "Sign-in didn't come back? Paste the address or code";

  function serveStart(start: Record<string, unknown>, bodies: unknown[] = []) {
    server.use(
      http.post(`${API_BASE}/oauth/connections/:id/authorize`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ device: null, authorization_url: "", ...start });
      }),
    );
  }

  it("has no paste box before any sign-in started", async () => {
    serveConnections(RELAY);
    renderSection("music");
    await screen.findByRole("button", { name: "Sign in with Example Music" });
    expect(screen.queryByRole("button", { name: PASTE_TOGGLE })).not.toBeInTheDocument();
  });

  it("offers the paste box after a relay sign-in starts, and finishes the sign-in from the pasted address", async () => {
    serveConnections(RELAY);
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    serveStart({ flow: "relay", authorization_url: "https://accounts.example.com/a" });
    const pasted: unknown[] = [];
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/complete`, async ({ request }) => {
        pasted.push(await request.json());
        return HttpResponse.json({ ...RELAY, status: "connected" });
      }),
    );
    const user = userEvent.setup();
    renderSection("music");
    await user.click(await screen.findByRole("button", { name: "Sign in with Example Music" }));

    const toggle = await screen.findByRole("button", { name: PASTE_TOGGLE });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    const address = "https://fiestaboard.app/auth/oauth/redirect?code=test_code&state=test_state";
    await user.type(screen.getByLabelText("Address or code"), address);
    await user.click(screen.getByRole("button", { name: "Finish sign-in" }));

    await waitFor(() => expect(pasted).toEqual([{ pasted: address }]));
  });

  it("still offers the paste box when the page is opened again after leaving for the provider", async () => {
    serveConnections(RELAY);
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    serveStart({ flow: "relay", authorization_url: "https://accounts.example.com/a" });
    const first = renderSection("music");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await screen.findByRole("button", { name: PASTE_TOGGLE });
    first.unmount();

    renderSection("music");
    expect(await screen.findByRole("button", { name: PASTE_TOGGLE })).toBeInTheDocument();
  });

  it("puts the paste box away once the sign-in came back, even when the board's clock is behind", async () => {
    serveConnections(RELAY);
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    serveStart({ flow: "relay", authorization_url: "https://accounts.example.com/a" });
    const first = renderSection("music");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await screen.findByRole("button", { name: PASTE_TOGGLE });
    first.unmount();

    // Back from the provider: connected, stamped by a board a minute slow.
    serveConnections({ ...RELAY, status: "connected", connected_at: Math.floor(Date.now() / 1000) - 60 });
    renderSection("music");
    await screen.findByRole("button", { name: "Disconnect" });
    expect(screen.queryByRole("button", { name: PASTE_TOGGLE })).not.toBeInTheDocument();
  });

  it("keeps the paste box when a reconnect has not come back yet", async () => {
    const earlier = Math.floor(Date.now() / 1000) - 3600;
    serveConnections({ ...RELAY, status: "connected", connected_at: earlier });
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign: vi.fn() });
    serveStart({ flow: "relay", authorization_url: "https://accounts.example.com/a" });
    const first = renderSection("music");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Reconnect" }));
    await screen.findByRole("button", { name: PASTE_TOGGLE });
    first.unmount();

    renderSection("music");
    expect(await screen.findByRole("button", { name: PASTE_TOGGLE })).toBeInTheDocument();
  });

  it("opens the paste box straight away when the sign-in cannot come back on its own", async () => {
    serveConnections(RELAY);
    const open = vi.fn();
    vi.stubGlobal("open", open);
    serveStart({
      flow: "relay",
      authorization_url: "https://auth.example.com/authorize?x=1",
      paste_expected: true,
      paste_hint: "Copy the whole address from the tab that shows 127.0.0.1:1455",
    });
    const user = userEvent.setup();
    renderSection("music");
    await user.click(await screen.findByRole("button", { name: "Sign in with Example Music" }));

    expect(await screen.findByLabelText("Address or code")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: PASTE_TOGGLE })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Copy the whole address from the tab that shows 127.0.0.1:1455")).toBeInTheDocument();
    // The board stays open in this tab, so the provider opens in another.
    expect(open).toHaveBeenCalledWith("https://auth.example.com/authorize?x=1", "_blank", "noopener,noreferrer");
    expect(screen.getByRole("link", { name: /Open the sign-in page again/ })).toHaveAttribute(
      "href",
      "https://auth.example.com/authorize?x=1",
    );
  });

  it("says why a pasted address was refused", async () => {
    serveConnections(RELAY);
    vi.stubGlobal("open", vi.fn());
    serveStart({ flow: "relay", authorization_url: "https://auth.example.com/a", paste_expected: true });
    server.use(
      http.post(`${API_BASE}/oauth/connections/music/complete`, () =>
        HttpResponse.json({ detail: "That sign-in has expired. Start again." }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderSection("music");
    await user.click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await user.type(await screen.findByLabelText("Address or code"), "test_code_1234");
    await user.click(screen.getByRole("button", { name: "Finish sign-in" }));
    expect(await screen.findByText("That sign-in has expired. Start again.")).toBeInTheDocument();
  });

  it("will not send an empty paste", async () => {
    serveConnections(RELAY);
    vi.stubGlobal("open", vi.fn());
    serveStart({ flow: "relay", authorization_url: "https://auth.example.com/a", paste_expected: true });
    const user = userEvent.setup();
    renderSection("music");
    await user.click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    expect(await screen.findByRole("button", { name: "Finish sign-in" })).toBeDisabled();
  });

  it("offers a sign-in without a redirect for a key-exchange provider, and asks for the code", async () => {
    const KEYS: OAuthConnection = { ...RELAY, flows: ["key_exchange"], user_app: false, client_id_setting: null };
    serveConnections(KEYS);
    vi.stubGlobal("open", vi.fn());
    const bodies: unknown[] = [];
    serveStart(
      { flow: "key_exchange", authorization_url: "https://keys.example.com/auth", paste_expected: true },
      bodies,
    );
    const user = userEvent.setup();
    renderSection("music");
    await user.click(await screen.findByRole("button", { name: "Sign in without a browser redirect" }));

    await waitFor(() => expect(bodies).toEqual([{ board_url: window.location.origin, headless: true }]));
    expect(await screen.findByLabelText("Address or code")).toBeInTheDocument();
  });

  it("waits for a Plex-style approval without showing a code", async () => {
    serveConnections({
      ...RELAY,
      flows: ["plex_pin"],
      user_app: false,
      client_id_setting: null,
      device: { ...PENDING_DEVICE, user_code: "", verification_uri: "", verification_uri_complete: "" },
    });
    renderSection("music");
    expect(await screen.findByText("Waiting for approval")).toBeInTheDocument();
    expect(screen.getByText(/Approve FiestaBoard in the Example Music tab/)).toBeInTheDocument();
    expect(screen.queryByTestId("oauth-user-code")).not.toBeInTheDocument();
  });

  it("opens a Plex-style sign-in in another tab so this page keeps watching", async () => {
    serveConnections({ ...RELAY, flows: ["plex_pin"], user_app: false, client_id_setting: null });
    const open = vi.fn();
    vi.stubGlobal("open", open);
    serveStart({
      flow: "plex_pin",
      authorization_url: "https://app.example.com/auth#?code=abc",
      device: { ...PENDING_DEVICE, user_code: "" },
    });
    renderSection("music");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in with Example Music" }));
    await waitFor(() =>
      expect(open).toHaveBeenCalledWith("https://app.example.com/auth#?code=abc", "_blank", "noopener,noreferrer"),
    );
  });

  it("says the provider stopped accepting the sign-in when the plugin reported it", async () => {
    serveConnections({ ...RELAY, status: "reauthorization_required", status_reason: "rejected" });
    renderSection("music");
    expect(await screen.findByText("Reconnect needed")).toBeInTheDocument();
    expect(screen.getByText("Example Music stopped accepting the sign-in. Sign in again.")).toBeInTheDocument();
  });
});

describe("a sign-in that can only finish by paste (ChatGPT's loopback redirect)", () => {
  const CHATGPT: OAuthConnection = {
    ...RELAY,
    id: "ai.gpt",
    kind: "ai",
    plugin_id: "ai",
    plugin_name: "ChatGPT (FiestaBot)",
    provider_name: "ChatGPT",
    user_app: false,
    shared_app: true,
    client_id_setting: null,
    paste_expected: true,
  };
  const AUTHORIZE_URL = "https://auth.example.com/api/accounts/authorize?client_id=dynamic_agent_client";
  const LANDED = "http://127.0.0.1:1455/auth/callback?code=test_code&state=test_state&client_id=oaiapp_test";

  /** A stand-in for the tab window.open returns, recording where it is sent. */
  function fakeTab() {
    return { closed: false, opener: {} as unknown, location: { replace: vi.fn() }, close: vi.fn() };
  }

  function renderPanel() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <OAuthConnectionPanel connectionId="ai.gpt" title="ChatGPT sign-in" />
      </QueryClientProvider>,
    );
  }

  function serveStart(answer: () => Promise<void> = async () => {}) {
    server.use(
      http.post(`${API_BASE}/oauth/connections/ai.gpt/authorize`, async () => {
        await answer();
        return HttpResponse.json({
          flow: "relay",
          device: null,
          authorization_url: AUTHORIZE_URL,
          paste_expected: true,
          paste_hint: "",
        });
      }),
    );
  }

  it("says before the click that the provider opens in a new tab and ends on a page that does not load", async () => {
    serveConnections(CHATGPT);
    renderPanel();
    await screen.findByRole("button", { name: "Sign in with ChatGPT" });
    expect(screen.getByText(/ChatGPT opens in a new tab/)).toBeInTheDocument();
    // The relay's "you come back by way of fiestaboard.app" is not true here.
    expect(screen.queryByText(/by way of fiestaboard.app/)).not.toBeInTheDocument();
  });

  it("opens the new tab in the click itself, before the board answers, so no popup blocker stops it", async () => {
    serveConnections(CHATGPT);
    const tab = fakeTab();
    const open = vi.fn(() => tab);
    vi.stubGlobal("open", open);
    let answer!: () => void;
    serveStart(() => new Promise<void>((resolve) => (answer = resolve)));
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, origin: window.location.origin, assign });
    const user = userEvent.setup();
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Sign in with ChatGPT" }));

    expect(open).toHaveBeenCalledTimes(1);
    expect(tab.location.replace).not.toHaveBeenCalled();
    // The provider's page never gets a handle on this one.
    expect(tab.opener).toBeNull();

    answer();
    await waitFor(() => expect(tab.location.replace).toHaveBeenCalledWith(AUTHORIZE_URL));
    // This tab stays on the board: it is where the address gets pasted.
    expect(assign).not.toHaveBeenCalled();
  });

  it("keeps this tab on an open, focused step 2 that says the dead end is expected", async () => {
    serveConnections(CHATGPT);
    vi.stubGlobal(
      "open",
      vi.fn(() => fakeTab()),
    );
    serveStart();
    const user = userEvent.setup();
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Sign in with ChatGPT" }));

    const step = await screen.findByRole("group", { name: "Finish signing in" });
    expect(within(step).getByText("Sign in to ChatGPT in the new tab.")).toBeInTheDocument();
    expect(within(step).getByText(/can't connect/)).toBeInTheDocument();
    expect(within(step).getByText(/That's expected/)).toBeInTheDocument();
    expect(within(step).getByText(/Copy the whole address/)).toBeInTheDocument();
    const field = within(step).getByLabelText("Address from the ChatGPT tab");
    await waitFor(() => expect(field).toHaveFocus());
    // Not tucked behind "didn't come back?": there is nothing to come back.
    expect(screen.queryByRole("button", { name: /didn't come back/ })).not.toBeInTheDocument();
    expect(within(step).getByRole("link", { name: /Open the sign-in page again/ })).toHaveAttribute(
      "href",
      AUTHORIZE_URL,
    );
  });

  it("offers a link to the provider when the browser blocked the new tab", async () => {
    serveConnections(CHATGPT);
    vi.stubGlobal(
      "open",
      vi.fn(() => null),
    );
    serveStart();
    const user = userEvent.setup();
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Sign in with ChatGPT" }));

    const step = await screen.findByRole("group", { name: "Finish signing in" });
    expect(within(step).getByText("Your browser blocked the new tab.")).toBeInTheDocument();
    expect(within(step).getByRole("link", { name: /Open the ChatGPT sign-in page/ })).toHaveAttribute(
      "href",
      AUTHORIZE_URL,
    );
  });

  it("closes the blank tab when the sign-in could not start", async () => {
    serveConnections(CHATGPT);
    const tab = fakeTab();
    vi.stubGlobal(
      "open",
      vi.fn(() => tab),
    );
    server.use(
      http.post(`${API_BASE}/oauth/connections/ai.gpt/authorize`, () =>
        HttpResponse.json({ detail: "The provider is unreachable." }, { status: 502 }),
      ),
    );
    const user = userEvent.setup();
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Sign in with ChatGPT" }));
    await waitFor(() => expect(tab.close).toHaveBeenCalled());
    expect(screen.queryByRole("group", { name: "Finish signing in" })).not.toBeInTheDocument();
  });

  it("refreshes FiestaBot's providers and their models once the sign-in finishes", async () => {
    serveConnections(CHATGPT);
    vi.stubGlobal(
      "open",
      vi.fn(() => fakeTab()),
    );
    serveStart();
    server.use(
      http.post(`${API_BASE}/oauth/connections/ai.gpt/complete`, () =>
        HttpResponse.json({ ...CHATGPT, status: "connected" }),
      ),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    render(
      <QueryClientProvider client={queryClient}>
        <OAuthConnectionPanel connectionId="ai.gpt" title="ChatGPT sign-in" />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Sign in with ChatGPT" }));
    await user.type(await screen.findByLabelText("Address from the ChatGPT tab"), LANDED);
    await user.click(screen.getByRole("button", { name: "Finish sign-in" }));

    await waitFor(() => {
      const keys = invalidate.mock.calls.map(([filters]) => JSON.stringify(filters?.queryKey));
      expect(keys).toContain(JSON.stringify(["ai-settings"]));
      expect(keys).toContain(JSON.stringify(["ai-provider-models", "gpt"]));
    });
  });

  it("finishes the sign-in from the pasted address and says so", async () => {
    serveConnections(CHATGPT);
    vi.stubGlobal(
      "open",
      vi.fn(() => fakeTab()),
    );
    serveStart();
    const pasted: unknown[] = [];
    server.use(
      http.post(`${API_BASE}/oauth/connections/ai.gpt/complete`, async ({ request }) => {
        pasted.push(await request.json());
        serveConnections({ ...CHATGPT, status: "connected", connected_at: Math.floor(Date.now() / 1000) });
        return HttpResponse.json({ ...CHATGPT, status: "connected" });
      }),
    );
    const user = userEvent.setup();
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Sign in with ChatGPT" }));
    await user.type(await screen.findByLabelText("Address from the ChatGPT tab"), LANDED);
    await user.click(screen.getByRole("button", { name: "Finish sign-in" }));

    await waitFor(() => expect(pasted).toEqual([{ pasted: LANDED }]));
    expect(await screen.findByText("Signed in to ChatGPT.")).toBeInTheDocument();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Finish signing in" })).not.toBeInTheDocument();
  });
});

describe("OAuthConnectionPanel", () => {
  it("shows any connection by its id, under the title it is given", async () => {
    serveConnections({
      ...RELAY,
      id: "ai.p1",
      kind: "ai",
      plugin_id: "ai",
      provider_name: "OpenRouter",
      flows: ["key_exchange"],
      user_app: false,
      client_id_setting: null,
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <OAuthConnectionPanel connectionId="ai.p1" title="OpenRouter sign-in" />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "OpenRouter sign-in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in with OpenRouter" })).toBeEnabled();
  });
});

describe("boardAddress", () => {
  it("is the origin the app is open at", () => {
    expect(boardAddress()).toBe(window.location.origin);
  });

  it("includes the path prefix when the app is served under one", () => {
    (window as WindowWithRouterContext).__reactRouterContext = { basename: "/api/hassio_ingress/tok123/" };
    expect(boardAddress()).toBe(`${window.location.origin}/api/hassio_ingress/tok123`);
  });
});

describe("readOAuthReturn", () => {
  it("reads a successful return", () => {
    expect(readOAuthReturn(new URLSearchParams("tab=installed&oauth=connected&plugin=music"))).toEqual({
      outcome: "connected",
      pluginId: "music",
      reason: null,
    });
  });

  it("reads a failed return that names no plugin", () => {
    expect(readOAuthReturn(new URLSearchParams("oauth=error&reason=invalid_state"))).toEqual({
      outcome: "error",
      pluginId: null,
      reason: "invalid_state",
    });
  });

  it.each(["", "tab=installed", "oauth=", "oauth=maybe"])("ignores a URL that is not a return (%s)", (query) => {
    expect(readOAuthReturn(new URLSearchParams(query))).toBeNull();
  });
});

describe("oauthReturnErrorKey", () => {
  it.each(["invalid_state", "expired", "access_denied", "exchange_failed", "provider_error"])(
    "has its own message for %s",
    (reason) => {
      expect(oauthReturnErrorKey(reason)).toBe(`returnError.${reason}`);
    },
  );

  it.each([null, "", "something_new", "constructor"])("falls back to a generic message for %s", (reason) => {
    expect(oauthReturnErrorKey(reason)).toBe("returnError.provider_error");
  });
});
