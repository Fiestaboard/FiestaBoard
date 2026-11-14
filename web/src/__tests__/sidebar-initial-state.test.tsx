import { render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { SidebarProvider, useSidebar } from "@/components/sidebar-context";

const originalMatchMedia = window.matchMedia;
afterEach(() => {
  window.matchMedia = originalMatchMedia;
  localStorage.removeItem("fiestaboard_sidebar_collapsed");
});

it("starts collapsed without animation on a tablet even with an expanded desktop preference", () => {
  localStorage.setItem("fiestaboard_sidebar_collapsed", "false");
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(min-width: 768px) and (max-width: 1023.98px)",
  }));
  const renders: { collapsed: boolean; transitioning: boolean }[] = [];
  function Probe() {
    const { collapsed, transitioning } = useSidebar();
    renders.push({ collapsed, transitioning });
    return null;
  }
  render(
    <SidebarProvider>
      <Probe />
    </SidebarProvider>,
  );
  expect(renders[0]).toEqual({ collapsed: true, transitioning: false });
  expect(localStorage.getItem("fiestaboard_sidebar_collapsed")).toBe("false");
});
