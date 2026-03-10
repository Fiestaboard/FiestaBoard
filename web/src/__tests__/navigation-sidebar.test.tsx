import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { SidebarProvider } from "@/components/sidebar-context";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

const API_BASE = "/api";

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
      <SidebarProvider>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            {children}
          </ThemeProvider>
        </ConfigOverridesProvider>
      </SidebarProvider>
    </QueryClientProvider>
  );
}

describe("NavigationSidebar active state", () => {
  // Active nav link uses bg-white/15 (sidebar gradient); desktop also uses bg-sidebar-accent in theme
  const activeNavClass = "bg-white/15";

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

describe("NavigationSidebar Monitor link", () => {
  beforeEach(() => {
    mockPathname.mockReturnValue("/");
  });

  it("does not show Monitor link when monitoring is disabled", async () => {
    server.use(
      http.get(`${API_BASE}/debug/monitor/enabled`, () =>
        HttpResponse.json({ enabled: false })
      )
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.queryByText("Monitor")).not.toBeInTheDocument();
    });
  });

  it("shows Monitor link when monitoring is enabled", async () => {
    server.use(
      http.get(`${API_BASE}/debug/monitor/enabled`, () =>
        HttpResponse.json({ enabled: true })
      )
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      const monitorLinks = screen.getAllByText("Monitor");
      expect(monitorLinks.length).toBeGreaterThan(0);
    });
  });

  it("Monitor link opens in new tab with target _blank", async () => {
    server.use(
      http.get(`${API_BASE}/debug/monitor/enabled`, () =>
        HttpResponse.json({ enabled: true })
      )
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      const monitorLinks = screen.getAllByText("Monitor");
      monitorLinks.forEach((link) => {
        const anchor = link.closest("a");
        expect(anchor).toHaveAttribute("target", "_blank");
        expect(anchor).toHaveAttribute("rel", "noopener noreferrer");
      });
    });
  });

  it("Monitor link href points to /grafana/", async () => {
    server.use(
      http.get(`${API_BASE}/debug/monitor/enabled`, () =>
        HttpResponse.json({ enabled: true })
      )
    );

    render(<NavigationSidebar />, { wrapper: TestWrapper });

    await waitFor(() => {
      const monitorLinks = screen.getAllByText("Monitor");
      monitorLinks.forEach((link) => {
        const anchor = link.closest("a");
        expect(anchor?.getAttribute("href")).toBe("/grafana/");
      });
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
