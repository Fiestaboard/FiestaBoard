/**
 * The BoardSelector hub line (slice 2.3, WEB-09; 07a `302:2146`): the address
 * this page was opened at, then Online / Remote / Can't reach with its dot,
 * from the shared status poll.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

/** Below 768px the tab bar and the header pill are the chrome (`matchMedia`). */
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

    const host = window.location.hostname;
    // No state is claimed until the hub has answered; then "host · Online".
    await waitFor(() => expect(hubLines().some((line) => line.textContent?.includes(`${host} · Online`))).toBe(true));
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

describe("one hub-state source", () => {
  const host = () => window.location.hostname;
  const pill = () => document.querySelector<HTMLElement>('[data-slot="board-selector-hub"]');

  async function openMore() {
    const user = userEvent.setup();
    const tabBar = document.querySelector<HTMLElement>('[data-slot="sidebar-bottom-nav"]')!;
    await user.click(within(tabBar).getByRole("button", { name: "More" }));
    return screen.getByRole("dialog", { name: "Navigation menu" });
  }

  it("gives the phone header pill its hub line: 'Online · host'", async () => {
    setPhone(true);
    twoBoards();
    render(<NavigationSidebar />, { wrapper: Wrapper });
    await waitFor(() => expect(pill()?.textContent).toContain(`Online · ${host()}`));
  });

  it.each([
    ["Online", () => HttpResponse.json({ running: true, initialized: true, config_summary: {} })],
    ["Can't reach", () => HttpResponse.error()],
  ])("the header pill and the More drawer's line say the same thing (%s)", async (word, answer) => {
    setPhone(true);
    twoBoards();
    server.use(
      http.get("/api/v1/status", answer),
      http.get("/api/version", () => HttpResponse.json({ running_version: "2.0.1" })),
    );
    render(<NavigationSidebar />, { wrapper: Wrapper });
    await waitFor(() => expect(pill()?.textContent).toContain(word), { timeout: 3000 });

    const drawer = await openMore();
    const line = await waitFor(() => {
      const el = drawer.querySelector<HTMLElement>('[data-slot="hub-line"]');
      expect(el?.textContent).toContain(`${host()} · ${word}`);
      return el!;
    });
    // Both read the same state, so their words match exactly.
    expect(pill()!.textContent).toContain(word);
    expect(line.textContent).not.toContain(word === "Online" ? "Can't reach" : "Online");
  });

  it("adds no status poll on a single-board install, where the switcher never shows", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <GlobalAiPanelProvider>
          <SidebarProvider>
            <CurrentBoardProvider>
              <ConfigOverridesProvider>
                <ThemeProvider attribute="class" defaultTheme="light">
                  <NavigationSidebar />
                </ThemeProvider>
              </ConfigOverridesProvider>
            </CurrentBoardProvider>
          </SidebarProvider>
        </GlobalAiPanelProvider>
      </QueryClientProvider>,
    );
    // The one board has loaded (the list rendered) and the switcher is absent.
    await screen.findAllByRole("link", { name: "Home" });
    await new Promise((r) => setTimeout(r, 150));
    expect(document.querySelector('[data-slot="board-selector-hub"]')).toBeNull();
    const status = queryClient.getQueryCache().find({ queryKey: ["status"] });
    expect(status?.state.dataUpdateCount ?? 0).toBe(0);
    expect(status?.state.errorUpdateCount ?? 0).toBe(0);
    expect(status?.state.fetchStatus ?? "idle").toBe("idle");
  });
});
