/**
 * BB-B-4 / BB-B-17 (Figma 57:64661): below the rail the page editor's own
 * header and toolbar replace the app's phone header and tab bar. A short
 * landscape phone keeps the phone chrome below lg (BB-A-13), so it gets the
 * takeover too. With the rail (tablets, desktop) the nav stays.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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

import { MainContent } from "@/components/main-content";
import { NavigationSidebar } from "@/components/navigation-sidebar";

/** `true`: portrait phone; `"landscape"`: 844x390 (short, below lg); `false`: tablet+. */
function setPhone(phone: boolean | "landscape") {
  const hits =
    phone === "landscape" ? ["max-height: 499.98px", "max-width: 1023.98px"] : phone ? ["max-width: 767.98px"] : [];
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: hits.some((h) => query.includes(h)),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function renderShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <GlobalAiPanelProvider>
        <SidebarProvider>
          <CurrentBoardProvider>
            <ConfigOverridesProvider>
              <NavigationSidebar />
              <MainContent>
                <p>content</p>
              </MainContent>
            </ConfigOverridesProvider>
          </CurrentBoardProvider>
        </SidebarProvider>
      </GlobalAiPanelProvider>
    </QueryClientProvider>,
  );
}

const nav = () => screen.queryAllByRole("navigation");
const main = () => document.getElementById("main-content");

beforeEach(() => setPhone(true));

describe("the page editor takes over the phone chrome", () => {
  it.each(["/pages/edit/p1", "/pages/new"])("draws no tab bar or phone header at %s on a phone", (path) => {
    mockPathname.mockReturnValue(path);
    renderShell();
    expect(nav()).toHaveLength(0);
    expect(main()?.className).not.toMatch(/pt-\[calc\(var\(--mobile-header-height/);
    expect(main()?.className).not.toMatch(/bottom-nav-offset/);
  });

  it("keeps the tab bar on the Pages list", () => {
    mockPathname.mockReturnValue("/pages");
    renderShell();
    expect(nav().length).toBeGreaterThan(0);
    expect(main()?.className).toMatch(/bottom-nav-offset/);
  });

  it("draws no tab bar or rail in the editor on a landscape phone (844x390)", () => {
    setPhone("landscape");
    mockPathname.mockReturnValue("/pages/edit/p1");
    renderShell();
    expect(nav()).toHaveLength(0);
  });

  it("keeps the rail in the editor from 768px", () => {
    setPhone(false);
    mockPathname.mockReturnValue("/pages/edit/p1");
    renderShell();
    expect(nav().length).toBeGreaterThan(0);
  });
});
