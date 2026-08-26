"use client";

import { MainContent as UIMainContent } from "@fiestaboard/ui";

import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { useSidebar } from "@/components/sidebar-context";
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
      onTransitionEnd={onTransitionEnd}
    >
      {children}
    </UIMainContent>
  );
}
