/**
 * Settings as a list-detail (slice 2.1, WEB-01; Figma 07e §1): a hub card,
 * the You group and the Settings › Hub group, each section at
 * /settings/:section. Old ?section= tab links still land in the right place.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "../../app/routes/settings";
import { server } from "./mocks/server";

const boardContext = { currentBoardId: "desk", boards: [{ id: "desk", name: "Desk" }], isLoading: false };

vi.mock("@/components/current-board-context", () => ({ useCurrentBoard: () => boardContext }));

vi.mock("@/hooks/use-router", async () => {
  const rr = await vi.importActual<typeof import("react-router")>("react-router");
  return {
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
    useSearchParams: () => rr.useSearchParams()[0],
    usePathname: () => "/settings",
    useParams: rr.useParams,
  };
});

vi.mock("@/components/wizard-provider", () => ({ useWizard: () => ({ triggerWizard: vi.fn() }) }));

// The shared setup stubs react-router's location hooks; this reads the real one.
const rrActual = await vi.importActual<typeof import("react-router")>("react-router");

function Where() {
  const location = rrActual.useLocation();
  return <div data-testid="where">{location.pathname + location.search + location.hash}</div>;
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/settings/:section?"
            element={
              <>
                <SettingsPage />
                <Where />
              </>
            }
          />
          <Route path="/displays/desk" element={<div>Desk playback settings</div>} />
          <Route path="/displays" element={<div>Choose a display</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function anchor(id: string): Element | null {
  return document.querySelector(`[data-ai-anchor="${id}"]`);
}

function setPhone(phone: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: phone && query.includes("max-width: 767.98px"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

const originalMatchMedia = window.matchMedia;

beforeEach(() => {
  boardContext.currentBoardId = "desk";
  boardContext.boards = [{ id: "desk", name: "Desk" }];
  setPhone(false);
  server.use(
    http.get("/api/network/wifi/capability", () => HttpResponse.json({ available: false })),
    http.get("/api/auth/mcp-token", () => HttpResponse.json({ configured: false, source: "none" })),
    http.get("/api/debug/system-info", () =>
      HttpResponse.json({
        board_ip: "192.168.1.1",
        server_ip: "192.168.1.2",
        uptime_seconds: 3600,
        uptime_formatted: "1h 0m",
        connection_mode: "local",
        version: "11.0.0",
        timestamp: "2026-11-13T12:00:00Z",
        cache_status: null,
        board_configured: true,
        service_running: true,
      }),
    ),
    http.get("/api/settings/all", () =>
      HttpResponse.json({ general: { timezone: "America/Los_Angeles", instance_name: "Maya’s FiestaPi" } }),
    ),
  );
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

describe("Settings index", () => {
  it("lists the You group in the 06 order: Account, Notifications, Appearance, Accessibility, FiestaBot", async () => {
    renderAt("/settings");
    const you = await screen.findByRole("list", { name: "You" });
    await waitFor(() =>
      expect(
        within(you)
          .getAllByRole("link")
          // The title alone: rows now read a value beside it ("System").
          .map((link) => link.querySelector('[data-slot="list-row-title"]')?.textContent),
      ).toEqual(["Account", "Notifications", "Appearance", "Accessibility", "FiestaBot"]),
    );
  });

  it("lists the Settings › Hub group, named for the hub: Network, AI provider, System & backups, Language & time", async () => {
    renderAt("/settings");
    const hub = await screen.findByRole("list", { name: "Hub · Maya’s FiestaPi" });
    const links = within(hub).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "Network",
      "AI provider",
      "System & backups",
      "Language & time",
    ]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/settings/network",
      "/settings/ai-provider",
      "/settings/system",
      "/settings/language-time",
    ]);
  });

  it("names the hub in a card at the head of the list, with its version", async () => {
    renderAt("/settings");
    const card = (await screen.findByText("Maya’s FiestaPi")).closest<HTMLElement>('[data-slot="settings-hub-card"]')!;
    await waitFor(() => expect(within(card).getByText(/Online · FiestaBoard 2\.0\.1/)).toBeInTheDocument());
  });

  it("hides Account while auth is on and nobody is signed in", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json({ enabled: true, authenticated: false, mode: "password", username: null }),
      ),
    );
    renderAt("/settings");
    const you = await screen.findByRole("list", { name: "You" });
    await waitFor(() => expect(within(you).queryByRole("link", { name: "Account" })).not.toBeInTheDocument());
  });
});

describe("Settings detail, from the rail breakpoint up", () => {
  it("opens FiestaBot without offering unsupported per-person controls", async () => {
    renderAt("/settings/fiestabot");
    expect(await screen.findByRole("heading", { level: 2, name: "FiestaBot" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "FiestaBot" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText(/Approval mode in the drawer applies to everyone on this hub/)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Auto" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it.each(["appearance", "network", "language-time", "system", "ai-provider"])(
    "gives each %s settings panel its own card surface",
    async (section) => {
      renderAt(`/settings/${section}`);
      const detail = await screen.findByRole("region", {
        name: screen.getByRole("heading", { level: 2 }).textContent!,
      });
      await waitFor(() => expect(detail.querySelectorAll('[data-slot="page-section"]').length).toBeGreaterThan(0));
      const panels = detail.querySelectorAll('[data-slot="page-section"]');
      for (const panel of panels) {
        expect(panel.parentElement).toHaveAttribute("data-slot", "page-card");
        expect(panel.parentElement?.querySelectorAll('[data-slot="page-section"]')).toHaveLength(1);
      }
    },
  );

  it("opens the first section beside the list when none is named", async () => {
    renderAt("/settings");
    expect(await screen.findByRole("heading", { level: 2, name: "Account" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("aria-current", "page");
  });

  it("marks the open section's row as current", async () => {
    renderAt("/settings/network");
    expect(await screen.findByRole("heading", { level: 2, name: "Network" })).toBeInTheDocument();
    const network = screen.getByRole("link", { name: "Network" });
    expect(network).toHaveAttribute("aria-current", "page");
    // The kit's selected state (07e inset pill), not an app-painted fill.
    expect(network).toHaveAttribute("data-selected");
    expect(network.className).not.toMatch(/(^|\s)bg-accent(\s|$)/);
    expect(await screen.findByRole("link", { name: "Account" })).not.toHaveAttribute("aria-current");
  });

  it("sends an unknown section to the index", async () => {
    renderAt("/settings/nope");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/settings$/));
  });

  it("sends a prototype key to the index too (no inherited lookups)", async () => {
    renderAt("/settings/toString");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/settings$/));
  });

  it("opens a deep-linked Account while auth status is still loading, with no Appearance flash", async () => {
    server.use(
      http.get("/api/auth/status", async () => {
        await new Promise((resolve) => setTimeout(resolve, 200));
        return HttpResponse.json({ enabled: false, authenticated: false, mode: "disabled", username: null });
      }),
    );
    renderAt("/settings/account");
    expect(screen.getByRole("heading", { level: 2, name: "Account" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Appearance" })).not.toBeInTheDocument();
  });

  it("sends a hidden Account to the index once auth status says it is hidden", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json({ enabled: true, authenticated: false, mode: "password", username: null }),
      ),
    );
    renderAt("/settings/account");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/settings$/));
  });

  it("shows actual browser and hub-reported addresses without inventing remote access", async () => {
    renderAt("/settings/network");
    expect(await screen.findByText("This browser is using")).toBeInTheDocument();
    expect(await screen.findByText("192.168.1.2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Set up remote access/ })).not.toBeInTheDocument();
  });

  it("puts MQTT under Network", async () => {
    renderAt("/settings/network");
    await waitFor(() => expect(anchor("settings.mqtt")).not.toBeNull());
  });

  it("keeps AI provider to AI providers and MCP", async () => {
    renderAt("/settings/ai-provider");
    await waitFor(() => expect(anchor("settings.ai")).not.toBeNull());
    expect(anchor("settings.mqtt")).toBeNull();
    expect(anchor("settings.plugins")).toBeNull();
  });

  it("puts the hub's name, updates, backups and diagnostics under System & backups, with no About card", async () => {
    renderAt("/settings/system");
    await waitFor(() => expect(anchor("settings.general")).not.toBeNull());
    await waitFor(() => expect(anchor("settings.release_channel")).not.toBeNull());
    await waitFor(() => expect(anchor("settings.debug")).not.toBeNull());
    expect(screen.queryByText("About This FiestaBoard")).not.toBeInTheDocument();
  });

  // BB-C-13 / 07e 320:8881: the Version card comes first, then Backups.
  it("opens System & backups with the Version card, then backups", async () => {
    renderAt("/settings/system");
    await waitFor(() => expect(anchor("settings.release_channel")).not.toBeNull());
    await waitFor(() => expect(anchor("settings.general")).not.toBeNull());
    const version = anchor("settings.release_channel")!;
    const backups = await screen.findByText("Backup & Restore");
    const follows = (a: Node, b: Node) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(version, backups)).toBe(true);
    expect(follows(backups, anchor("settings.general")!)).toBe(true);
  });

  it("opens the About box from System & backups, the only About entry a phone has", async () => {
    const user = userEvent.setup();
    renderAt("/settings/system");
    await user.click(await screen.findByRole("button", { name: "About FiestaBoard" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("puts location and time under Language & time", async () => {
    renderAt("/settings/language-time");
    await waitFor(() => expect(anchor("settings.location")).not.toBeNull());
  });

  it("labels the theme as a browser preference with touch-sized choices", async () => {
    renderAt("/settings/appearance");
    expect(await screen.findByRole("heading", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByText("For this browser only.")).toBeInTheDocument();
    expect(screen.getByText("Theme for this browser; preview motion for everyone on this hub.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "System" })).toHaveClass("min-h-12");
  });

  it("describes supported motion scope without unsupported reading controls", async () => {
    renderAt("/settings/accessibility");
    expect(await screen.findByText("Motion preferences apply to everyone on this hub.")).toBeInTheDocument();
    const toggle = await screen.findByRole("switch", { name: "Reduce motion" });
    expect(screen.queryByText("Motion and reading comfort in this browser.")).not.toBeInTheDocument();
    expect(toggle).toHaveAccessibleDescription("Minimizes animations throughout the interface");
    expect(screen.queryByRole("switch", { name: "Read board changes aloud" })).not.toBeInTheDocument();
  });

  it("keeps board previews and flip speed under Appearance", async () => {
    renderAt("/settings/appearance");
    expect(await screen.findByRole("radiogroup", { name: "Flip speed" })).toBeInTheDocument();
    expect(anchor("settings.display")).not.toBeNull();
  });

  it("keeps board scheduling out of app-wide settings", async () => {
    for (const section of ["appearance", "network", "system", "language-time"]) {
      const { unmount } = renderAt(`/settings/${section}`);
      await screen.findByRole("heading", { level: 2 });
      expect(anchor("settings.polling")).toBeNull();
      expect(anchor("settings.schedule_behavior")).toBeNull();
      unmount();
    }
  });
});

describe("Settings below the rail breakpoint (phone)", () => {
  it("shows the list alone at /settings", async () => {
    setPhone(true);
    renderAt("/settings");
    expect(await screen.findByRole("list", { name: "You" })).toBeInTheDocument();
    expect(document.querySelector('[data-slot="settings-detail"]')).toBeNull();
    expect(await screen.findByRole("link", { name: "Account" })).not.toHaveAttribute("aria-current");
  });

  it("shows a section alone, as the page's h1, with a way back to the list", async () => {
    setPhone(true);
    renderAt("/settings/system");
    expect(await screen.findByRole("heading", { level: 1, name: "System & backups" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "You" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
  });
});

describe("Old ?section= links", () => {
  it.each([
    ["general", "/settings/appearance"],
    ["account", "/settings/account"],
    ["ai", "/settings/ai-provider"],
    ["integrations", "/settings/ai-provider"],
    ["system", "/settings/system"],
    ["advanced", "/settings/system"],
    ["network", "/settings/network"],
  ])("?section=%s lands on %s", async (section, target) => {
    renderAt(`/settings?section=${section}`);
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(target));
  });

  it.each([
    ["location", "/settings/language-time#location"],
    ["language", "/settings/language-time#language"],
    ["time", "/settings/language-time#time"],
    ["time-and-date", "/settings/language-time#time-and-date"],
    ["timezone", "/settings/language-time#timezone"],
    ["mqtt", "/settings/network#mqtt"],
    ["instance-name", "/settings/system#instance-name"],
    ["general", "/settings/system#general"],
    ["appearance", "/settings/appearance#appearance"],
    ["reduce-motion", "/settings/appearance#reduce-motion"],
  ])("?section=general#%s lands on %s, keeping the anchor", async (hash, target) => {
    window.location.hash = `#${hash}`;
    try {
      renderAt(`/settings?section=general`);
      await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(target));
    } finally {
      window.location.hash = "";
    }
  });

  it.each([
    ["location", "language-time"],
    ["language", "language-time"],
    ["time", "language-time"],
    ["mqtt", "network"],
    ["instance-name", "system"],
    ["general", "system"],
  ])("scrolls and highlights the actual #%s card after redirect", async (hash, section) => {
    window.location.hash = `#${hash}`;
    try {
      renderAt("/settings?section=general");
      await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(`/settings/${section}#${hash}`));
      await waitFor(() => expect(document.getElementById(hash)).toHaveClass("settings-anchor-highlight"));
    } finally {
      window.location.hash = "";
    }
  });

  it("ignores a ?section= that is only an inherited object key", async () => {
    renderAt("/settings?section=toString");
    expect(await screen.findByRole("list", { name: "You" })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/settings\?section=toString$/);
  });

  it("keeps the anchor on any old tab link", async () => {
    window.location.hash = "#ai-enabled";
    try {
      renderAt("/settings?section=ai");
      await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/settings/ai-provider#ai-enabled"));
    } finally {
      window.location.hash = "";
    }
  });

  it("keeps the other query parameters (the AI provider's OAuth return)", async () => {
    renderAt("/settings?section=ai&oauth=done");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/settings/ai-provider?oauth=done"));
  });

  it.each(["behavior", "scheduling"])("?section=%s opens the current display", async (section) => {
    renderAt(`/settings?section=${section}`);
    expect(await screen.findByText("Desk playback settings")).toBeInTheDocument();
  });

  it("sends an old scheduling link to the display list when there is no board", async () => {
    boardContext.currentBoardId = "";
    boardContext.boards = [];
    renderAt("/settings?section=scheduling");
    expect(await screen.findByText("Choose a display")).toBeInTheDocument();
  });
});

describe("setup entry availability", () => {
  it("does not offer a setup action the provider refuses on an installed hub", async () => {
    Object.assign(boardContext.boards[0], { output_config: { host: "192.0.2.60", local_api_key: "***" } });
    renderAt("/settings/system");
    await waitFor(() => expect(anchor("settings.general")).not.toBeNull());
    expect(screen.queryByRole("button", { name: /run setup wizard/i })).not.toBeInTheDocument();
  });
  it("keeps setup available on a hub without displays", async () => {
    boardContext.boards = [];
    renderAt("/settings/system");
    expect(await screen.findByRole("button", { name: /run setup wizard/i })).toBeEnabled();
  });
});

describe("Settings index at 390 (07e `320:7936`, BB-C-23)", () => {
  it("heads the phone list with a way back to More and a plain, left-aligned title", async () => {
    setPhone(true);
    // The shell's More tab (FiestaUI Sidebar bottom-nav), which the back link reopens.
    const more = document.createElement("button");
    more.setAttribute("data-slot", "sidebar-bottom-nav-more");
    const opened = vi.fn();
    more.addEventListener("click", opened);
    document.body.appendChild(more);
    try {
      renderAt("/settings");
      const back = await screen.findByRole("button", { name: "More" });
      expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
      // 07e draws no gear and no blurb under the phone title.
      expect(screen.queryByText("Your account, this browser and this hub.")).not.toBeInTheDocument();
      await userEvent.click(back);
      expect(opened).toHaveBeenCalledTimes(1);
    } finally {
      more.remove();
    }
  });

  it("shows each row's current value where the hub has one", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json({
          enabled: true,
          authenticated: true,
          mode: "enabled",
          username: "maya",
          setup_required: false,
          first_run: false,
          session_management_supported: true,
        }),
      ),
      http.get("/api/auth/sessions", () =>
        HttpResponse.json({
          current_session_id: "a",
          sessions: ["a", "b", "c", "d"].map((id) => ({
            id,
            kind: "browser",
            device_name: "Desktop",
            method: "password",
            created_at: "2026-11-01T00:00:00Z",
            last_active_at: "2026-11-01T00:00:00Z",
            expires_at: "2027-11-01T00:00:00Z",
          })),
        }),
      ),
      http.get("/api/push/status", () =>
        HttpResponse.json({
          public_key: "k",
          user_enabled: true,
          device_enabled: true,
          subscribed: true,
          expiration_time: null,
          event_sources: [],
          test_available: false,
        }),
      ),
      http.get("/api/settings/ai", () =>
        HttpResponse.json({
          enabled: true,
          default_provider_id: "local",
          providers: [{ id: "local", name: "Ollama", base_url: "http://ollama:11434", api_key: "", models: [] }],
        }),
      ),
    );
    renderAt("/settings");
    const you = await screen.findByRole("list", { name: "You" });
    const row = (name: string) => within(you).getByRole("link", { name: new RegExp(`^${name}`) });
    await waitFor(() => expect(row("Account")).toHaveTextContent("maya · 4 signed-in devices"));
    await waitFor(() => expect(row("Notifications")).toHaveTextContent(/On$/));
    expect(row("Appearance")).toHaveTextContent(/System$/);
    await waitFor(() => expect(row("FiestaBot")).toHaveTextContent(/Ollama$/));
  });
});

describe("Account at 390 (BB-C-24)", () => {
  it("lays the account cards straight on the page, not inside another card", async () => {
    setPhone(true);
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json({ enabled: true, authenticated: true, mode: "enabled", username: "maya" }),
      ),
    );
    renderAt("/settings/account");
    await screen.findByRole("heading", { level: 1, name: "Account" });
    const detail = document.querySelector('[data-slot="settings-detail"]')!;
    expect(detail.querySelector('[data-slot="page-card"]')).toBeNull();
  });
});
