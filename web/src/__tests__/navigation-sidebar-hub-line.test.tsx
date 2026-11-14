/**
 * The BoardSelector hub line (slice 2.3, WEB-09; 07a `302:2146`): the address
 * this page was opened at, then Online / Remote / Can't reach with its dot,
 * from the shared status poll.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { SidebarProvider } from "@/components/sidebar-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const mockPathname = vi.fn(() => "/");
vi.mock("@/hooks/use-router", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

import { NavigationSidebar } from "@/components/navigation-sidebar";

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

function twoBoards() {
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        board_type: "black",
        boards: [
          { id: "kitchen", name: "Kitchen board", device_type: "flagship" },
          { id: "clock", name: "Entry clock", device_type: "flagship" },
        ],
        devices: ["flagship"],
      }),
    ),
  );
}

function hubLines(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-slot="board-selector-hub"]'));
}

describe("NavigationSidebar hub line", () => {
  it("reads 'host · Online' on the home network while the hub answers", async () => {
    twoBoards();
    render(<NavigationSidebar />, { wrapper: Wrapper });

    await waitFor(() => expect(hubLines().length).toBeGreaterThan(0));
    const host = window.location.hostname;
    expect(hubLines().some((line) => line.textContent?.includes(`${host} · Online`))).toBe(true);
  });

  it("reads Can't reach once the status poll gets no answer", async () => {
    twoBoards();
    server.use(http.get("/api/v1/status", () => HttpResponse.error()));
    render(<NavigationSidebar />, { wrapper: Wrapper });

    await waitFor(() => expect(hubLines().some((line) => line.textContent?.includes("Can't reach"))).toBe(true), {
      timeout: 3000,
    });
  });

  it("asks the hub nothing on a chromeless screen (the TV viewer)", async () => {
    mockPathname.mockReturnValue("/p/1");
    let statusCalls = 0;
    twoBoards();
    server.use(
      http.get("/api/v1/status", () => {
        statusCalls += 1;
        return HttpResponse.json({ running: true, initialized: true, config_summary: {} });
      }),
    );
    render(<NavigationSidebar />, { wrapper: Wrapper });
    await new Promise((r) => setTimeout(r, 100));
    expect(statusCalls).toBe(0);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    mockPathname.mockReturnValue("/");
  });
});
