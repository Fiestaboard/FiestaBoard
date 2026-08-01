"use client";

import { MainContent as UIMainContent } from "@fiestaboard/ui";

import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { useSidebar } from "@/components/sidebar-context";
import { usePathname } from "@/hooks/use-router";
import { MAX_APP_WIDTH } from "@/lib/layout-constants";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed, transitioning, onTransitionEnd } = useSidebar();
  const { isOpen: aiPanelOpen } = useGlobalAiPanel();
  const pathname = usePathname();
  // Auth screens render edge-to-edge with no sidebar — drop the chrome
  // padding so the login form centers in the actual viewport.
  const isAuthScreen = pathname.startsWith("/login");

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
