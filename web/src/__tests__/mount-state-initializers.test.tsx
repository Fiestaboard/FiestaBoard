import { render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InstallPrompt } from "@/components/install-prompt";
import { SidebarProvider, useSidebar } from "@/components/sidebar-context";

const pushSpy = vi.fn();
vi.mock("@/hooks/use-view-transition", () => ({
  useViewTransition: () => ({ push: pushSpy }),
}));
vi.mock("@/components/page-builder", () => ({
  PageBuilder: ({ pageId }: { pageId: string }) => <div data-testid="page-builder">{pageId}</div>,
}));

// Imported after the mocks so the route picks them up.
const { default: EditPage } = await import("../../app/routes/pages.edit._index");
const { default: OfflinePage } = await import("../../app/routes/offline");

/**
 * These five all read a browser API on mount and pushed the result into state
 * from a `useEffect` — the `react-hooks/set-state-in-effect` shape in issue
 * #1568, and a guaranteed extra render of the wrong thing. They now read it in
 * the `useState` initializer (safe: the app is a static SPA, `ssr: false`).
 *
 * The assertions deliberately look at the FIRST synchronous render, with no
 * `waitFor` — that is the difference between the two implementations.
 */
describe("browser state read on the first render", () => {
  describe("SidebarProvider", () => {
    function ShowsCollapsed() {
      const { collapsed } = useSidebar();
      return <output data-testid="collapsed">{String(collapsed)}</output>;
    }

    beforeEach(() => window.localStorage.clear());
    afterEach(() => window.localStorage.clear());

    it("renders collapsed on the first render when that is the stored preference", () => {
      window.localStorage.setItem("fiestaboard_sidebar_collapsed", "true");

      render(
        <SidebarProvider>
          <ShowsCollapsed />
        </SidebarProvider>,
      );

      expect(screen.getByTestId("collapsed").textContent).toBe("true");
    });

    it("renders expanded when nothing is stored", () => {
      render(
        <SidebarProvider>
          <ShowsCollapsed />
        </SidebarProvider>,
      );

      expect(screen.getByTestId("collapsed").textContent).toBe("false");
    });
  });

  describe("OfflinePage", () => {
    afterEach(() => vi.restoreAllMocks());

    it("shows the reconnecting state on the first render when the browser is online", () => {
      vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);

      render(<OfflinePage />);

      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Reconnecting...");
    });

    it("shows the offline state on the first render when the browser is offline", () => {
      vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

      render(<OfflinePage />);

      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("You're Offline");
    });
  });

  describe("EditPage", () => {
    afterEach(() => {
      pushSpy.mockClear();
      window.history.replaceState({}, "", "/");
    });

    it("mounts the page builder on the first render when ?id is in the URL", () => {
      window.history.replaceState({}, "", "/pages/edit?id=abc123");

      render(<EditPage />);

      // Never the "Loading..." placeholder — the id was in the URL all along.
      expect(screen.getByTestId("page-builder").textContent).toBe("abc123");
    });

    it("redirects to the pages list when ?id is missing", () => {
      window.history.replaceState({}, "", "/pages/edit");

      render(<EditPage />);

      expect(pushSpy).toHaveBeenCalledWith("/pages", { transitionType: "slide-down" });
    });
  });

  describe("InstallPrompt", () => {
    afterEach(() => vi.restoreAllMocks());

    it("renders nothing when the app is already running standalone", () => {
      vi.spyOn(window, "matchMedia").mockImplementation(
        (query: string) => ({ matches: query === "(display-mode: standalone)" }) as MediaQueryList,
      );

      const { container } = render(<InstallPrompt />);

      expect(container).toBeEmptyDOMElement();
    });
  });
});
