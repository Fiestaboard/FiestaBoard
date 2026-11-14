/**
 * Settings as a list-detail (slice 2.1, WEB-01; Figma 07e §1): a hub card,
 * the You group and the Settings › Hub group, each section at
 * /settings/:section. Old ?section= tab links still land in the right place.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
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
  return <div data-testid="where">{location.pathname + location.search}</div>;
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
    http.get("/api/settings/all", () =>
      HttpResponse.json({ general: { timezone: "America/Los_Angeles", instance_name: "Maya’s FiestaPi" } }),
    ),
  );
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

describe("Settings index", () => {
  it("lists the You group: Account, Appearance, Accessibility", async () => {
    renderAt("/settings");
    const you = await screen.findByRole("list", { name: "You" });
    await waitFor(() =>
      expect(
        within(you)
          .getAllByRole("link")
          .map((link) => link.textContent),
      ).toEqual(["Account", "Appearance", "Accessibility"]),
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
  it("opens the first section beside the list when none is named", async () => {
    renderAt("/settings");
    expect(await screen.findByRole("heading", { level: 2, name: "Account" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("aria-current", "page");
  });

  it("marks the open section's row as current", async () => {
    renderAt("/settings/network");
    expect(await screen.findByRole("heading", { level: 2, name: "Network" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Network" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("link", { name: "Account" })).not.toHaveAttribute("aria-current");
  });

  it("falls back to the first section for an unknown one", async () => {
    renderAt("/settings/nope");
    expect(await screen.findByRole("heading", { level: 2, name: "Account" })).toBeInTheDocument();
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

  it("puts location and time under Language & time", async () => {
    renderAt("/settings/language-time");
    await waitFor(() => expect(anchor("settings.location")).not.toBeNull());
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
