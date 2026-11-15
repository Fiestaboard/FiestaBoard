"use client";

import { MainContent as UIMainContent } from "@fiestaboard/ui";

import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { useSidebar } from "@/components/sidebar-context";
import { RAIL_BREAKPOINT } from "@/hooks/use-below-rail";
import { usePathname } from "@/hooks/use-router";
import { isChromelessPath } from "@/lib/chromeless";
import { MAX_APP_WIDTH } from "@/lib/layout-constants";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed, transitioning, onTransitionEnd } = useSidebar();
  const { isOpen: aiPanelOpen } = useGlobalAiPanel();
  const pathname = usePathname();
  // Chrome-less screens (login, FiestaPanel viewer) render edge-to-edge
  // with no sidebar — drop the chrome padding so they fill the viewport.
  const isAuthScreen = isChromelessPath(pathname);

  return (
    <UIMainContent
      collapsed={collapsed}
      transitioning={transitioning}
      aiPanelOpen={aiPanelOpen}
      isAuthScreen={isAuthScreen}
      maxWidth={MAX_APP_WIDTH}
      // The same breakpoint as NavigationSidebar (WEB-02), and room at the
      // foot for its tab bar below it, so nothing hides behind the bar.
      railBreakpoint={RAIL_BREAKPOINT}
      bottomNav
      onTransitionEnd={onTransitionEnd}
    >
      {children}
    </UIMainContent>
  );
}
