import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { SidebarProvider } from "@/components/sidebar-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";

// Mock usePathname from next/navigation
const mockPathname = vi.fn();
vi.mock("next/navigation", () => ({
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

    const backdrop = document.querySelector('[aria-hidden="true"]');
    if (backdrop) {
      fireEvent.click(backdrop);
    }

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

  it("shows Carousels item in primary navigation", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const carouselsLinks = screen.getAllByText("Carousels");
    expect(carouselsLinks.length).toBeGreaterThan(0);
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

describe("NavigationSidebar carousels link", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("Carousels is a direct link to /carousels", () => {
    render(<NavigationSidebar />, { wrapper: TestWrapper });

    const carouselsLinks = screen.getAllByText("Carousels");
    const carouselsLink = carouselsLinks[0].closest("a");
    expect(carouselsLink).toBeInTheDocument();
    expect(carouselsLink).toHaveAttribute("href", "/carousels");
  });
});
