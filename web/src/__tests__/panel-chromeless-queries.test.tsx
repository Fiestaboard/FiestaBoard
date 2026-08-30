/**
 * The FiestaPanel TV viewer mounts the full provider tree, but must not fire
 * the app shell's authenticated queries: an unauthenticated TV browser would
 * spam 401s (times the retry count) on every wall-display load and bury real
 * panel errors in console noise.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { SidebarProvider } from "@/components/sidebar-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { FormatPreferencesProvider } from "@/hooks/use-format-preferences";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const mockPathname = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

// Must import after mocking.
import { GlobalAiChatDrawer } from "@/components/global-ai-chat-drawer";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { ReduceMotionApplier } from "@/components/reduce-motion-applier";

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ScheduleEditorBridgeProvider>
        <PageEditorBridgeProvider>
          <GlobalAiPanelProvider>
            <SidebarProvider>
              <CurrentBoardProvider>
                <ConfigOverridesProvider>
                  <FormatPreferencesProvider>
                    <ThemeProvider attribute="class" defaultTheme="light">
                      {children}
                    </ThemeProvider>
                  </FormatPreferencesProvider>
                </ConfigOverridesProvider>
              </CurrentBoardProvider>
            </SidebarProvider>
          </GlobalAiPanelProvider>
        </PageEditorBridgeProvider>
      </ScheduleEditorBridgeProvider>
    </QueryClientProvider>
  );
}

/** Count requests to the app-shell endpoints the TV must never call. */
function trackShellRequests() {
  const hits: string[] = [];
  server.use(
    http.get("/api/settings/board", () => {
      hits.push("/settings/board");
      return HttpResponse.json({ board_type: "black", boards: [], devices: [] });
    }),
    http.get("/api/settings/all", () => {
      hits.push("/settings/all");
      return HttpResponse.json({});
    }),
    http.get("/api/settings/ai", () => {
      hits.push("/settings/ai");
      return HttpResponse.json({ enabled: false, providers: [] });
    }),
    http.get("/api/settings/beta", () => {
      hits.push("/settings/beta");
      return HttpResponse.json({ settings: { transition_plugins_enabled: false } });
    }),
  );
  return hits;
}

describe("chromeless routes do not fire app-shell queries", () => {
  afterEach(() => {
    window.history.pushState({}, "", "/");
  });

  /** Everything the root layout mounts on every route, panel viewer included. */
  function AppShell() {
    return (
      <>
        <ReduceMotionApplier />
        <NavigationSidebar />
        <GlobalAiChatDrawer />
      </>
    );
  }

  it("panel viewer path: no board/settings/ai/beta requests", async () => {
    window.history.pushState({}, "", "/panel/abc123def456");
    mockPathname.mockReturnValue("/panel/abc123def456");
    const hits = trackShellRequests();

    render(<AppShell />, { wrapper: Wrapper });
    // Give any (wrongly) enabled query a beat to fire.
    await new Promise((resolve) => setTimeout(resolve, 200));

    expect(hits).toEqual([]);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("app path: the same queries do fire", async () => {
    window.history.pushState({}, "", "/pages");
    mockPathname.mockReturnValue("/pages");
    const hits = trackShellRequests();

    render(<AppShell />, { wrapper: Wrapper });
    await new Promise((resolve) => setTimeout(resolve, 200));

    expect(hits).toContain("/settings/board");
    expect(hits).toContain("/settings/ai");
    expect(hits).toContain("/settings/beta");
    expect(hits).toContain("/settings/all");
  });
});
