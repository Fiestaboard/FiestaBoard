import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider, useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { SidebarProvider } from "@/components/sidebar-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

// Mock usePathname from next/navigation
const mockPathname = vi.fn();
const mockPush = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

// Must import after mocking
import { NavigationSidebar } from "@/components/navigation-sidebar";

/** Below 768px the tab bar is the nav (WEB-01/02); `matchMedia` decides which list the Sidebar gets. */
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

beforeEach(() => setPhone(false));

/** Says whether the global FiestaBot panel is open, so a test can see a row open it. */
function AiPanelProbe() {
  const { isOpen } = useGlobalAiPanel();
  return <span data-testid="ai-panel-probe">{isOpen ? "open" : "closed"}</span>;
}

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <GlobalAiPanelProvider>
        <SidebarProvider>
          <AiPanelProbe />
          <CurrentBoardProvider>
            <ConfigOverridesProvider>
              <ThemeProvider attribute="class" defaultTheme="light">
                {children}
              </ThemeProvider>
            </ConfigOverridesProvider>
          </CurrentBoardProvider>
        </SidebarProvider>
      </GlobalAiPanelProvider>
    </QueryClientProvider>
  );
}

describe("NavigationSidebar active state", () => {
  const activeNavClass = "nav-active";

  it("highlights Pages when on /pages", () => {
    mockPathname.mockReturnValue("/pages");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const pagesLinks = screen.getAllByText("Pages");
    pagesLinks.forEach((link) => {
      expect(link.closest("a")).toHaveClass(activeNavClass);
    });
  });

  it("highlights Pages when on /pages/edit/123", () => {
    mockPathname.mockReturnValue("/pages/edit/123");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const pagesLinks = screen.getAllByText("Pages");
    pagesLinks.forEach((link) => {
      expect(link.closest("a")).toHaveClass(activeNavClass);
    });
  });

  it("highlights Pages when on /pages/new", () => {
    mockPathname.mockReturnValue("/pages/new");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const pagesLinks = screen.getAllByText("Pages");
    pagesLinks.forEach((link) => {
      expect(link.closest("a")).toHaveClass(activeNavClass);
    });
  });

  it("does not highlight Pages when on /", () => {
    mockPathname.mockReturnValue("/");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const pagesLinks = screen.getAllByText("Pages");
    pagesLinks.forEach((link) => {
      expect(link.closest("a")).not.toHaveClass(activeNavClass);
    });
  });

  it("has a Displays item that links to /displays (plan D21)", () => {
    mockPathname.mockReturnValue("/");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const links = screen.getAllByText("Displays").map((label) => label.closest("a"));
    expect(links.length).toBeGreaterThan(0);
    links.forEach((link) => expect(link).toHaveAttribute("href", "/displays"));
  });

  it("lists the rail in IA order: Home · Pages · Collections · Schedule · Displays │ Integrations · Staff Picks · Settings · Help & Docs", () => {
    mockPathname.mockReturnValue("/");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const rail = screen.getByRole("complementary", { name: "Main navigation" });
    const nav = within(rail).getByRole("navigation", { name: "Primary navigation" });
    const labels = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent?.trim());
    expect(labels).toEqual([
      "Home",
      "Pages",
      "Collections",
      "Schedule",
      "Displays",
      "Integrations",
      "Staff Picks",
      "Settings",
      "Help & Docs",
    ]);
  });

  it("highlights Displays on a display's own page", () => {
    mockPathname.mockReturnValue("/displays/board-2");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    screen.getAllByText("Displays").forEach((label) => {
      expect(label.closest("a")).toHaveClass(activeNavClass);
    });
  });

  it("highlights Home only on exact /", () => {
    mockPathname.mockReturnValue("/");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const homeLinks = screen.getAllByText("Home");
    homeLinks.forEach((link) => {
      expect(link.closest("a")).toHaveClass(activeNavClass);
    });
  });

  it("does not highlight Home on /pages", () => {
    mockPathname.mockReturnValue("/pages");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const homeLinks = screen.getAllByText("Home");
    homeLinks.forEach((link) => {
      expect(link.closest("a")).not.toHaveClass(activeNavClass);
    });
  });
});

describe("NavigationSidebar bottom nav (below 768px)", () => {
  const tabBar = () => document.querySelector<HTMLElement>('[data-slot="sidebar-bottom-nav"]')!;

  beforeEach(() => {
    setPhone(true);
    mockPathname.mockReturnValue("/");
  });

  it("puts Home, Pages, Schedule and Displays on the tab bar, then More", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const labels = Array.from(tabBar().querySelectorAll("a, button")).map((el) => el.textContent?.trim());
    expect(labels).toEqual(["Home", "Pages", "Schedule", "Displays", "More"]);
  });

  it("lights the Pages tab on /collections, which nests inside Pages", () => {
    mockPathname.mockReturnValue("/collections/c1");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(within(tabBar()).getByRole("link", { name: "Pages" })).toHaveAttribute("aria-current", "page");
    expect(within(tabBar()).queryByRole("link", { name: "Collections" })).not.toBeInTheDocument();
  });

  it("opens More with the rest of the IA: Integrations, Staff Picks, Settings, Help & Docs", async () => {
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    const more = within(drawer).getByRole("navigation", { name: "More" });
    expect(
      within(more)
        .getAllByRole("link")
        .map((link) => link.textContent?.trim()),
    ).toEqual(["Integrations", "Staff Picks", "Settings", "Help & Docs"]);
  });

  it("shows the Settings › Hub group in More, named for the hub, with the hub line at its foot", async () => {
    server.use(
      http.get("/api/settings/all", () => HttpResponse.json({ general: { instance_name: "Maya’s FiestaPi" } })),
    );
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    const hub = await within(drawer).findByRole("list", { name: "Hub · Maya’s FiestaPi" });
    expect(
      within(hub)
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual(["/settings/network", "/settings/ai-provider", "/settings/system", "/settings/language-time"]);
    await waitFor(() => expect(within(drawer).getByText(/Online · FiestaBoard 2\.0\.1/)).toBeInTheDocument());
  });

  it("divides the nav group from the Hub group even with no FiestaBot row (07a)", async () => {
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    expect(within(drawer).queryByRole("button", { name: /FiestaBot/ })).not.toBeInTheDocument();
    const divider = drawer.querySelector('[data-slot="more-divider"]');
    const hub = await within(drawer).findByRole("list", { name: /^Hub · / });
    expect(divider).not.toBeNull();
    // The hairline comes before the Hub heading in reading order.
    expect(divider!.compareDocumentPosition(hub) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("lights the Hub group row for the section you are on", async () => {
    mockPathname.mockReturnValue("/settings/network");
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    const hub = await within(drawer).findByRole("list", { name: /^Hub · / });
    expect(within(hub).getByRole("link", { name: "Network" })).toHaveAttribute("aria-current", "page");
    expect(within(hub).getByRole("link", { name: "AI provider" })).not.toHaveAttribute("aria-current");
  });

  it("keeps the account rows out of More: they live in Settings", async () => {
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    expect(within(drawer).queryByRole("radiogroup", { name: "Appearance" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: /Sign out/ })).not.toBeInTheDocument();
  });

  it("closes More when a Hub group row is chosen", async () => {
    // The rows are the app's, not the Sidebar's: they reach the drawer's
    // close through the slot's `closeMenu`, or the route would change under
    // a drawer that stayed open.
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    await user.click(within(drawer).getByRole("link", { name: "Network" }));

    expect(screen.queryByRole("dialog", { name: "Navigation menu" })).not.toBeInTheDocument();
  });

  it("closes More when its backdrop is clicked", async () => {
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    // Off the menu: setup.ts gives every element a 100×20 box at (0, 0).
    fireEvent.click(screen.getByTestId("mobile-backdrop"), { clientX: 300, clientY: 500 });

    expect(screen.queryByRole("dialog", { name: "Navigation menu" })).not.toBeInTheDocument();
  });

  it("offers FiestaBot in More when a provider is set up, and opening it closes More", async () => {
    server.use(
      http.get("/api/settings/ai", () =>
        HttpResponse.json({
          enabled: true,
          providers: [{ id: "p1", name: "OpenRouter", base_url: "", api_key: "", models: [] }],
          default_provider_id: "p1",
        }),
      ),
    );
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await user.click(within(tabBar()).getByRole("button", { name: "More" }));
    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    await user.click(await within(drawer).findByRole("button", { name: /FiestaBot/ }));

    expect(screen.queryByRole("dialog", { name: "Navigation menu" })).not.toBeInTheDocument();
    // And it opened the global FiestaBot drawer.
    expect(screen.getByTestId("ai-panel-probe")).toHaveTextContent("open");
  });
});

describe("NavigationSidebar rail", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("takes over from the tab bar at 768px (railBreakpoint md, WEB-02)", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(screen.getByRole("complementary", { name: "Main navigation" })).toHaveAttribute(
      "data-rail-breakpoint",
      "md",
    );
  });

  it("shows collapse/expand sidebar toggle", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const collapseButton = screen.getByLabelText("Collapse sidebar");
    expect(collapseButton).toBeInTheDocument();

    fireEvent.click(collapseButton);

    const expandButton = screen.getByLabelText("Expand sidebar");
    expect(expandButton).toBeInTheDocument();
  });
});

describe("NavigationSidebar tablet band (768–1023px)", () => {
  function setTablet() {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("min-width: 768px") && query.includes("max-width: 1023.98px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }

  beforeEach(() => {
    mockPathname.mockReturnValue("/");
    localStorage.removeItem("fiestaboard_sidebar_collapsed");
  });

  it("starts the rail collapsed (07 61:17544)", () => {
    setTablet();
    render(<NavigationSidebar />, { wrapper: TestWrapper });
    expect(screen.getByLabelText("Expand sidebar")).toBeInTheDocument();
  });

  it("lets the reader expand it there without overwriting the wide-screen preference", () => {
    localStorage.setItem("fiestaboard_sidebar_collapsed", "true");
    setTablet();
    render(<NavigationSidebar />, { wrapper: TestWrapper });
    fireEvent.click(screen.getByLabelText("Expand sidebar"));
    expect(screen.getByLabelText("Collapse sidebar")).toBeInTheDocument();
    expect(localStorage.getItem("fiestaboard_sidebar_collapsed")).toBe("true");
  });

  it("persists the toggle on a wide screen, as before", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });
    fireEvent.click(screen.getByLabelText("Collapse sidebar"));
    expect(localStorage.getItem("fiestaboard_sidebar_collapsed")).toBe("true");
  });
});

describe("NavigationSidebar Integrations badge (07a: one badge, one story)", () => {
  function servePlugins(plugins: Array<Record<string, unknown>>) {
    server.use(
      http.get("/api/plugins", () =>
        HttpResponse.json({ plugins, plugin_system_enabled: true, total: plugins.length, enabled_count: 0 }),
      ),
    );
  }

  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("badges Integrations with the count of integrations that need setting up, in words", async () => {
    servePlugins([
      { id: "weather", enabled: true, configured: false, plugin_type: "data" },
      { id: "stocks", enabled: true, configured: true, plugin_type: "data" },
    ]);
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const rail = screen.getByRole("complementary", { name: "Main navigation" });
    await waitFor(() =>
      expect(within(rail).getByRole("link", { name: "Integrations, 1 needs attention" })).toBeInTheDocument(),
    );
  });

  it("rolls the badge up onto More on a phone", async () => {
    setPhone(true);
    servePlugins([{ id: "weather", enabled: true, configured: false, plugin_type: "data" }]);
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const tabBar = document.querySelector<HTMLElement>('[data-slot="sidebar-bottom-nav"]')!;
    await waitFor(() =>
      expect(within(tabBar).getByRole("button", { name: "More, 1 needs attention" })).toBeInTheDocument(),
    );
  });

  it("draws no badge when everything is set up", async () => {
    servePlugins([{ id: "stocks", enabled: true, configured: true, plugin_type: "data" }]);
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const rail = screen.getByRole("complementary", { name: "Main navigation" });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(rail).getByRole("link", { name: "Integrations" })).toBeInTheDocument();
  });
});

/*
 * @fiestaboard/ui v5.12 collapsed the rail's two nav landmarks into one flat
 * list; 7.0.0 then took the assistant and Settings OUT of it. The list is
 * destinations only — places you can be — so these tests assert its
 * CONTENTS, which is what the app actually promises, and no longer the shape
 * of the container they happen to sit in.
 */
describe("NavigationSidebar nav list", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("renders a single navigation landmark per rail", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    // getAllBy, not getBy: the desktop <aside> and the mobile menu each
    // render their own copy of the one list.
    const navs = screen.getAllByLabelText("Primary navigation");
    expect(navs.length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Secondary navigation")).not.toBeInTheDocument();
  });

  it("shows Collections in the nav list", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const collectionsLinks = screen.getAllByText("Collections");
    expect(collectionsLinks.length).toBeGreaterThan(0);
  });

  it("lists Settings in the nav list (WEB-01), and lights it on its sections", () => {
    mockPathname.mockReturnValue("/settings/network");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const rail = screen.getByRole("complementary", { name: "Main navigation" });
    const nav = within(rail).getByRole("navigation", { name: "Primary navigation" });
    expect(within(nav).getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");
  });

  it("reaches Settings from the account menu", async () => {
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const triggers = document.querySelectorAll<HTMLElement>('[data-slot="sidebar-account-trigger"]');
    expect(triggers.length).toBeGreaterThan(0);
    await user.click(triggers[0]);

    const popup = await screen.findByRole("dialog", { name: "Account menu" });
    mockPush.mockClear();
    await user.click(within(popup).getByRole("button", { name: "Settings" }));
    expect(mockPush).toHaveBeenCalledWith("/settings");
  });

  it("shows Help & Docs in the nav list", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const helpLinks = screen.getAllByText("Help & Docs");
    expect(helpLinks.length).toBeGreaterThan(0);
  });

  it("does not show Profile (folded into Settings)", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(screen.queryByText("Profile")).not.toBeInTheDocument();
  });
});

describe("NavigationSidebar settings shortcut", () => {
  /** The gear in the desktop rail's footer. The mobile drawer has no gear — it lists Settings inline. */
  const gear = () =>
    within(
      screen
        .getByRole("complementary", { name: "Main navigation" })
        .querySelector<HTMLElement>('[data-slot="sidebar-footer"]')!,
    ).getByRole("link", { name: "Settings" });

  it("links straight to /settings from the rail footer", () => {
    mockPathname.mockReturnValue("/");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(gear()).toHaveAttribute("href", "/settings");
    expect(gear().closest('[data-slot="sidebar-footer"]')).not.toBeNull();
  });

  it("leaves the gear unlit on /settings: the Settings row says where you are (07e)", () => {
    mockPathname.mockReturnValue("/settings");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(gear()).not.toHaveAttribute("aria-current");
    expect(gear()).not.toHaveClass("nav-active");
  });

  it("leaves the gear unlit on every other route", () => {
    mockPathname.mockReturnValue("/pages");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(gear()).not.toHaveAttribute("aria-current");
    expect(gear()).not.toHaveClass("nav-active");
  });
});

describe("NavigationSidebar update notice", () => {
  /** The rail's account trigger. The mobile drawer has none — its rows render inline. */
  const accountTrigger = () =>
    within(screen.getByRole("complementary", { name: "Main navigation" })).getByRole("button", {
      name: "More",
    });

  const moreTab = () => document.querySelector<HTMLElement>('[data-slot="sidebar-bottom-nav-more"]')!;

  /** Serve an update state, and report once the sidebar has asked for both halves of it. */
  function mockUpdate({ available, managedExternally }: { available: boolean; managedExternally: boolean }) {
    const served = { status: false, check: false };
    server.use(
      http.get("/api/system/update/status", () => {
        served.status = true;
        return HttpResponse.json({ updater_available: true, managed_externally: managedExternally });
      }),
      http.get("/api/system/update-check", () => {
        served.check = true;
        return HttpResponse.json({ update_available: available, latest_version: available ? "8.39.0" : "8.38.9" });
      }),
    );
    return async () => {
      await waitFor(() => expect(served).toEqual({ status: true, check: true }));
      // One more turn for React Query to hand the responses to the render.
      await new Promise((resolve) => setTimeout(resolve, 0));
    };
  }

  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("marks the account trigger when an update is waiting", async () => {
    mockUpdate({ available: true, managedExternally: false });
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    // The "Update to …" item was already in the menu; what was missing is
    // any sign on the closed button that the menu was worth opening.
    await waitFor(() => expect(accountTrigger()).toHaveAccessibleDescription("Update available"));
  });

  it("marks More on the tab bar when an update is waiting", async () => {
    mockUpdate({ available: true, managedExternally: false });
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    // FLOW-DESIGNER-BRIEF #8: More gets a badge for Update available.
    await waitFor(() => expect(moreTab()).toHaveAccessibleName("More, Update available"));
  });

  it("marks nothing when the install is current", async () => {
    const settled = mockUpdate({ available: false, managedExternally: false });
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await settled();
    expect(accountTrigger()).toHaveAccessibleDescription("");
    expect(moreTab()).toHaveAccessibleName("More");
  });

  it("marks nothing when an external supervisor owns updates", async () => {
    // The Home Assistant add-on case: FiestaBoard cannot apply the update, so
    // a dot pointing at it would be an offer it cannot honour.
    const settled = mockUpdate({ available: true, managedExternally: true });
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await settled();
    expect(accountTrigger()).toHaveAccessibleDescription("");
    expect(moreTab()).toHaveAccessibleName("More");
  });
});

describe("NavigationSidebar collections link", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("Collections is a direct link to /collections", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const collectionsLinks = screen.getAllByText("Collections");
    const collectionsLink = collectionsLinks[0].closest("a");
    expect(collectionsLink).toBeInTheDocument();
    expect(collectionsLink).toHaveAttribute("href", "/collections");
  });
});

describe("NavigationSidebar logo", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  // Was the Pride-Month celebrate button (issue #1204). @fiestaboard/ui 4.0.0
  // retired seasons, so the app passes no `onLogoClick` and Sidebar renders the
  // lockup as a plain non-interactive element. Kept as a regression guard: a
  // logo that silently becomes a button again is a keyboard-nav change nothing
  // else in the suite would catch.
  it("renders the logo area as non-interactive", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(screen.queryByRole("button", { name: /celebrate/i })).not.toBeInTheDocument();
  });
});

describe("NavigationSidebar AI Assistant visibility (issue #806)", () => {
  const API_BASE = "/api";

  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("hides AI Assistant button when AI is disabled, even with providers configured", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: false,
          providers: [
            {
              id: "p1",
              name: "OpenRouter",
              base_url: "https://openrouter.ai/api/v1",
              api_key: "sk-test",
              models: ["openai/gpt-4o-mini"],
              default_model: "openai/gpt-4o-mini",
            },
          ],
          default_provider_id: "p1",
        }),
      ),
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "AI Assistant" })).not.toBeInTheDocument();
    });
  });

  it("shows AI Assistant button when AI is enabled with providers", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [
            {
              id: "p1",
              name: "OpenRouter",
              base_url: "https://openrouter.ai/api/v1",
              api_key: "sk-test",
              models: ["openai/gpt-4o-mini"],
              default_model: "openai/gpt-4o-mini",
            },
          ],
          default_provider_id: "p1",
        }),
      ),
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "AI Assistant" }).length).toBeGreaterThan(0);
    });
  });

  it("keeps the assistant out of the nav list entirely", async () => {
    // The dual-highlight bug: as a nav row, opening the drawer over /pages
    // lit Pages AND AI Assistant at once. Out of the list, the route
    // highlight is the only thing the list can say.
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [
            {
              id: "p1",
              name: "OpenRouter",
              base_url: "https://openrouter.ai/api/v1",
              api_key: "sk-test",
              models: ["openai/gpt-4o-mini"],
              default_model: "openai/gpt-4o-mini",
            },
          ],
          default_provider_id: "p1",
        }),
      ),
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "AI Assistant" }).length).toBeGreaterThan(0);
    });
    for (const nav of screen.getAllByLabelText("Primary navigation")) {
      expect(within(nav).queryByRole("button", { name: "AI Assistant" })).not.toBeInTheDocument();
    }
  });

  it("hides AI Assistant button when AI is enabled but no providers configured", async () => {
    server.use(
      http.get(`${API_BASE}/settings/ai`, () =>
        HttpResponse.json({
          enabled: true,
          providers: [],
          default_provider_id: null,
        }),
      ),
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "AI Assistant" })).not.toBeInTheDocument();
    });
  });
});

describe("NavigationSidebar board selector (issue #1246)", () => {
  const API_BASE = "/api";

  beforeEach(() => {
    mockPathname.mockReturnValue("/");
    localStorage.clear();
  });

  function mockBoards(boards: Array<{ id: string; name: string }>) {
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        HttpResponse.json({
          board_type: "black",
          boards: boards.map((b) => ({ ...b, device_type: "flagship", board_color: "black" })),
          devices: ["flagship"],
        }),
      ),
    );
  }

  it("hides the selector for single-board installs", async () => {
    mockBoards([{ id: "default", name: "Flagship" }]);

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    // Give the board-settings query time to resolve, then assert absence.
    await waitFor(() => {
      expect(screen.getAllByLabelText("Primary navigation").length).toBeGreaterThan(0);
    });
    expect(screen.queryByLabelText("Select board to manage")).not.toBeInTheDocument();
  });

  it("shows the selector when more than one board is configured", async () => {
    mockBoards([
      { id: "one", name: "Kitchen" },
      { id: "two", name: "Office" },
    ]);

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    // Desktop sidebar + mobile drawer each render a trigger.
    await waitFor(() => {
      expect(screen.getAllByLabelText("Select board to manage").length).toBeGreaterThan(0);
    });
  });

  it("opens the dropdown and lists all configured boards", async () => {
    const user = userEvent.setup();
    mockBoards([
      { id: "one", name: "Kitchen" },
      { id: "two", name: "Office" },
    ]);

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const triggers = await screen.findAllByLabelText("Select board to manage");
    await user.click(triggers[0]);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: "Kitchen" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Office" })).toBeInTheDocument();
  });

  it("restores the persisted board selection across reloads", async () => {
    const user = userEvent.setup();
    localStorage.setItem("fiestaboard_current_board", "two");
    mockBoards([
      { id: "one", name: "Kitchen" },
      { id: "two", name: "Office" },
    ]);

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const triggers = await screen.findAllByLabelText("Select board to manage");
    await user.click(triggers[0]);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });
    // The persisted board ("Office") is the selected option when the menu opens.
    expect(screen.getByRole("option", { name: "Office" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("option", { name: "Kitchen" })).toHaveAttribute("aria-selected", "false");
  });
});
