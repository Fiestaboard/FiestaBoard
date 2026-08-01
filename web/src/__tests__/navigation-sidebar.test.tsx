import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

// Mock usePrideActive so tests can toggle the pride-month logo state
// without colliding with the calendar. Defaults to false to match the
// non-pride code path used by the existing suite.
const mockPrideActive = vi.fn(() => false);
const PRIDE_SEASON_MOCK = {
  id: "pride",
  label: "Pride",
  months: [5],
  htmlClass: "pride-month",
  colors: ["#e40303", "#ff8c00", "#ffed00", "#008026", "#004dff", "#750787"],
};
vi.mock("@/hooks/use-pride-active", () => ({
  usePrideActive: () => mockPrideActive(),
  useActiveSeason: () => (mockPrideActive() ? PRIDE_SEASON_MOCK : null),
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

describe("NavigationSidebar primary/secondary sections", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("renders primary navigation section", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const primaryNav = screen.getAllByLabelText("Primary navigation");
    expect(primaryNav.length).toBeGreaterThan(0);
  });

  it("renders secondary navigation section", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const secondaryNav = screen.getAllByLabelText("Secondary navigation");
    expect(secondaryNav.length).toBeGreaterThan(0);
  });

  it("shows Collections item in primary navigation", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const collectionsLinks = screen.getAllByText("Collections");
    expect(collectionsLinks.length).toBeGreaterThan(0);
  });

  it("shows Settings in secondary navigation", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const settingsLinks = screen.getAllByText("Settings");
    expect(settingsLinks.length).toBeGreaterThan(0);
  });

  it("shows Help & Docs in secondary navigation", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const helpLinks = screen.getAllByText("Help & Docs");
    expect(helpLinks.length).toBeGreaterThan(0);
  });

  it("does not show Profile in secondary navigation (folded into Settings)", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(screen.queryByText("Profile")).not.toBeInTheDocument();
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

describe("NavigationSidebar pride logo accessibility (issue #1204)", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
    mockPrideActive.mockReturnValue(false);
  });

  it("renders the logo area as a non-interactive div when Pride Month is inactive", () => {
    mockPrideActive.mockReturnValue(false);
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    expect(screen.queryByRole("button", { name: "Celebrate Pride Month" })).not.toBeInTheDocument();
  });

  it("renders the logo area as a keyboard-accessible button during Pride Month", () => {
    mockPrideActive.mockReturnValue(true);
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    // Both the mobile header and the desktop sidebar render a celebrate button.
    const celebrateButtons = screen.getAllByRole("button", { name: "Celebrate Pride Month" });
    expect(celebrateButtons.length).toBeGreaterThanOrEqual(2);
    celebrateButtons.forEach((button) => {
      expect(button.tagName).toBe("BUTTON");
      expect(button).toHaveAttribute("type", "button");
    });
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
      expect(screen.queryByText("AI Assistant")).not.toBeInTheDocument();
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
      expect(screen.getAllByText("AI Assistant").length).toBeGreaterThan(0);
    });
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
      expect(screen.queryByText("AI Assistant")).not.toBeInTheDocument();
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
