import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { SidebarProvider } from "@/components/sidebar-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

// Mock usePathname from next/navigation
const mockPathname = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

// Must import after mocking
import { NavigationSidebar } from "@/components/navigation-sidebar";

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

  it("lists the sections in order: Home, Displays, Pages, Collections, Schedule, Integrations", () => {
    mockPathname.mockReturnValue("/");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const nav = screen.getAllByRole("navigation", { name: "Primary navigation" })[0];
    const labels = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent?.trim());
    expect(labels.slice(0, 6)).toEqual(["Home", "Displays", "Pages", "Collections", "Schedule", "Integrations"]);
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

describe("NavigationSidebar mobile menu", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("toggles mobile menu on button click", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const menuButton = screen.getByLabelText("Open menu");
    fireEvent.click(menuButton);

    const closeButton = screen.getByLabelText("Close menu");
    expect(closeButton).toBeInTheDocument();
  });

  it("closes mobile menu when backdrop is clicked", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const menuButton = screen.getByLabelText("Open menu");
    fireEvent.click(menuButton);

    const backdrop = screen.getByTestId("mobile-backdrop");
    fireEvent.click(backdrop);

    expect(screen.getByLabelText("Open menu")).toBeInTheDocument();
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

  it("keeps Settings out of the nav list", () => {
    // Settings lives in the footer — a gear and an account-menu item. A nav
    // row for it competed for height with the destinations that actually
    // scroll.
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    for (const nav of screen.getAllByLabelText("Primary navigation")) {
      expect(within(nav).queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    }
  });

  it("reaches Settings from the account menu", async () => {
    const user = userEvent.setup();
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const triggers = document.querySelectorAll<HTMLElement>('[data-slot="sidebar-account-trigger"]');
    expect(triggers.length).toBeGreaterThan(0);
    await user.click(triggers[0]);

    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "Settings" })).toBeInTheDocument();
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
    within(screen.getByRole("complementary", { name: "Main navigation" })).getByRole("link", { name: "Settings" });

  it("links straight to /settings from the rail footer", () => {
    mockPathname.mockReturnValue("/");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(gear()).toHaveAttribute("href", "/settings");
    expect(gear().closest('[data-slot="sidebar-footer"]')).not.toBeNull();
  });

  it("marks the gear as the current page on /settings", () => {
    // Settings has no row in the nav list, so on /settings the gear is the
    // only thing on the rail that can say where you are.
    mockPathname.mockReturnValue("/settings");
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(gear()).toHaveAttribute("aria-current", "page");
    expect(gear()).toHaveClass("nav-active");
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

  it("marks the closed hamburger when an update is waiting", async () => {
    mockUpdate({ available: true, managedExternally: false });
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    // The drawer has no trigger to wear the dot, so the same notice goes on
    // the one control that opens it.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Open menu" })).toHaveAccessibleDescription("Update available"),
    );
  });

  it("marks nothing when the install is current", async () => {
    const settled = mockUpdate({ available: false, managedExternally: false });
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await settled();
    expect(accountTrigger()).toHaveAccessibleDescription("");
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAccessibleDescription("");
  });

  it("marks nothing when an external supervisor owns updates", async () => {
    // The Home Assistant add-on case: FiestaBoard cannot apply the update, so
    // a dot pointing at it would be an offer it cannot honour.
    const settled = mockUpdate({ available: true, managedExternally: true });
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await settled();
    expect(accountTrigger()).toHaveAccessibleDescription("");
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAccessibleDescription("");
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
