/**
 * Owner decision D1 (BB-E-3), wired through the real SidebarProvider and
 * NavigationSidebar: the editor collapses the nav to the icon rail for the
 * visit; leaving gives the global (stored) choice back; an explicit toggle
 * made in the editor becomes the global choice. In the tablet band a toggle
 * stays a session choice (DD-W46), editor or not.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { SidebarProvider } from "@/components/sidebar-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";

const mockPathname = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

import { NavigationSidebar } from "@/components/navigation-sidebar";

const KEY = "fiestaboard_sidebar_collapsed";
const TABLET = "(min-width: 768px) and (max-width: 1023.98px)";

function setViewport(tablet: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: tablet && query === TABLET,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function renderShell(path: string) {
  mockPathname.mockReturnValue(path);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => (
    <QueryClientProvider client={queryClient}>
      <GlobalAiPanelProvider>
        <SidebarProvider>
          <CurrentBoardProvider>
            <ConfigOverridesProvider>
              <NavigationSidebar />
            </ConfigOverridesProvider>
          </CurrentBoardProvider>
        </SidebarProvider>
      </GlobalAiPanelProvider>
    </QueryClientProvider>
  );
  const view = render(tree());
  return {
    navigate(next: string) {
      mockPathname.mockReturnValue(next);
      act(() => view.rerender(tree()));
    },
  };
}

const expandButton = () => screen.queryByRole("button", { name: "Expand sidebar" });
const collapseButton = () => screen.queryByRole("button", { name: "Collapse sidebar" });

beforeEach(() => {
  localStorage.clear();
  setViewport(false);
});

describe("D1: the nav rail in the page editor (wide screens)", () => {
  it("is the collapsed rail in the editor while the global choice stays expanded", () => {
    const app = renderShell("/pages");
    expect(collapseButton()).not.toBeNull();
    app.navigate("/pages/edit/p1");
    expect(expandButton()).not.toBeNull();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("comes back expanded on leaving the editor", () => {
    const app = renderShell("/pages/edit/p1");
    expect(expandButton()).not.toBeNull();
    app.navigate("/pages");
    expect(collapseButton()).not.toBeNull();
  });

  it("stays collapsed everywhere when the reader expands then collapses it in the editor", async () => {
    const user = userEvent.setup();
    const app = renderShell("/pages/new");
    await user.click(expandButton()!);
    expect(localStorage.getItem(KEY)).toBe("false");
    await user.click(collapseButton()!);
    expect(localStorage.getItem(KEY)).toBe("true");
    app.navigate("/");
    expect(expandButton()).not.toBeNull();
  });

  it("stays expanded on leaving when the reader expanded it in the editor", async () => {
    const user = userEvent.setup();
    const app = renderShell("/pages/edit/p1");
    await user.click(expandButton()!);
    app.navigate("/schedule");
    expect(collapseButton()).not.toBeNull();
    expect(localStorage.getItem(KEY)).toBe("false");
  });

  it("does not collapse again when a first save moves /pages/new to /pages/edit/:id", async () => {
    const user = userEvent.setup();
    const app = renderShell("/pages/new");
    await user.click(expandButton()!);
    app.navigate("/pages/edit/p1");
    expect(collapseButton()).not.toBeNull();
  });

  it("keeps a collapsed global choice collapsed after the editor", () => {
    localStorage.setItem(KEY, "true");
    const app = renderShell("/pages/edit/p1");
    app.navigate("/pages");
    expect(expandButton()).not.toBeNull();
    expect(localStorage.getItem(KEY)).toBe("true");
  });
});

describe("D1 in the tablet band", () => {
  it("keeps a toggle made in the editor a session choice there (DD-W46)", async () => {
    setViewport(true);
    const user = userEvent.setup();
    renderShell("/pages/edit/p1");
    await user.click(expandButton()!);
    expect(collapseButton()).not.toBeNull();
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});
