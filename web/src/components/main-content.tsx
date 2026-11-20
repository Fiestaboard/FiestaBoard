"use client";

import { MainContent as UIMainContent } from "@fiestaboard/ui";

import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { useSidebar } from "@/components/sidebar-context";
import { useBelowRail, useRailBreakpoint } from "@/hooks/use-below-rail";
import { usePathname } from "@/hooks/use-router";
import { isChromelessPath, isPageEditorPath } from "@/lib/chromeless";
import { MAX_APP_WIDTH } from "@/lib/layout-constants";

export function MainContent({ children }: { children: React.ReactNode }) {
  const railBreakpoint = useRailBreakpoint();
  const { collapsed, transitioning, onTransitionEnd } = useSidebar();
  const { isOpen: aiPanelOpen } = useGlobalAiPanel();
  const pathname = usePathname();
  // Chrome-less screens (login, FiestaPanel viewer) render edge-to-edge
  // with no sidebar — drop the chrome padding so they fill the viewport.
  // Below the rail the page editor takes the whole screen too: its toolbar
  // replaces the tab bar (BB-B-17), so no room is kept for either bar.
  const belowRail = useBelowRail();
  const isAuthScreen = isChromelessPath(pathname) || (belowRail && isPageEditorPath(pathname));

  return (
    <UIMainContent
      collapsed={collapsed}
      transitioning={transitioning}
      aiPanelOpen={aiPanelOpen}
      isAuthScreen={isAuthScreen}
      maxWidth={MAX_APP_WIDTH}
      // The same breakpoint as NavigationSidebar (WEB-02), and room at the
      // foot for its tab bar below it, so nothing hides behind the bar.
      railBreakpoint={railBreakpoint}
      bottomNav
      onTransitionEnd={onTransitionEnd}
    >
      {children}
    </UIMainContent>
  );
}
