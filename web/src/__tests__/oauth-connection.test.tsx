/**
 * The "Account connection" section of a plugin's settings sheet, and the
 * helpers that read an OAuth sign-in's outcome off the URL it returns to.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OAuthConnectionSection, oauthReturnErrorKey, readOAuthReturn } from "@/components/plugin-settings";
import { boardAddress, type OAuthConnection } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";
const REDIRECT_URI = "https://fiestaboard.app/auth/oauth/redirect.html";

const RELAY: OAuthConnection = {
  id: "music",
  plugin_id: "music",
  instance_label: null,
  plugin_name: "Music",
  provider_name: "Example Music",
  flows: ["relay"],
  configured: true,
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

function renderSection(pluginId: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <OAuthConnectionSection pluginId={pluginId} />
    </QueryClientProvider>,
  );
}

type WindowWithRouterContext = Window & { __reactRouterContext?: { basename?: string } };

afterEach(() => {
  vi.unstubAllGlobals();
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
    expect(await screen.findByRole("button", { name: "Connect to Example Music" })).toBeEnabled();
    // The status line is a live region, so a change is announced, not just recoloured.
    expect(screen.getByText("Not connected")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
  });

  it("will not start a connection until a client ID is saved, and says why", async () => {
    serveConnections({ ...RELAY, configured: false });
    renderSection("music");
    const connect = await screen.findByRole("button", { name: "Connect to Example Music" });
    expect(connect).toBeDisabled();
    expect(screen.getByText(/Enter a client ID in the settings below and save/)).toBeInTheDocument();
    expect(connect).toHaveAccessibleDescription(/Enter a client ID in the settings below and save/);
  });

  it("shows the redirect URI to register with the provider", async () => {
    serveConnections(RELAY);
    renderSection("music");
    expect(await screen.findByText(REDIRECT_URI)).toBeInTheDocument();
    expect(screen.getByText("Redirect URI")).toBeInTheDocument();
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

  it("does not mention the relay for a device-flow plugin", async () => {
    serveConnections(DEVICE);
    renderSection("git");
    await screen.findByRole("button", { name: "Connect to Example Git" });
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
    await userEvent.setup().click(await screen.findByRole("button", { name: "Connect to Example Music" }));
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
    await userEvent.setup().click(await screen.findByRole("button", { name: "Connect to Example Music" }));
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
    await userEvent.setup().click(await screen.findByRole("button", { name: "Connect to Example Git" }));

    expect(await screen.findByTestId("oauth-user-code")).toHaveTextContent("WDJB-MJHT");
    expect(screen.getByText("Waiting for approval")).toHaveAttribute("role", "status");
    // The code on screen is the thing to act on; the button now only replaces it.
    expect(screen.getByRole("button", { name: "Get a new code" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect to Example Git" })).not.toBeInTheDocument();
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
    await userEvent.setup().click(await screen.findByRole("button", { name: "Connect to Example Music" }));
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
    await userEvent.setup().click(await screen.findByRole("button", { name: "Connect to Example Music" }));
    await waitFor(() => expect(requested).toEqual(["music:kitchen"]));
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
