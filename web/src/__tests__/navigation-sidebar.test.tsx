import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "@/hooks/use-theme";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { SidebarProvider } from "@/components/sidebar-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";

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
          <ConfigOverridesProvider>
            <ThemeProvider attribute="class" defaultTheme="light">
              {children}
            </ThemeProvider>
          </ConfigOverridesProvider>
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
