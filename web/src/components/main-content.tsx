"use client";

import { cn } from "@/lib/utils";
import { MAX_APP_WIDTH } from "@/lib/layout-constants";
import { useSidebar } from "@/components/sidebar-context";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed, transitioning, onTransitionEnd } = useSidebar();
  const { isOpen: aiPanelOpen } = useGlobalAiPanel();

  return (
    <main
      className={cn(
        "h-screen flex flex-col pt-[72px] lg:pt-0 overflow-x-hidden overflow-y-auto w-full mx-auto sidebar-transition",
        collapsed ? "lg:pl-[76px]" : "lg:pl-[268px]",
        aiPanelOpen ? "lg:pr-[384px]" : "lg:pr-0",
        transitioning && "is-transitioning"
      )}
      style={{ maxWidth: MAX_APP_WIDTH }}
      onTransitionEnd={(e) => {
        if (e.target === e.currentTarget && e.propertyName === "padding-left") {
          onTransitionEnd();
        }
      }}
    >
      {children}
    </main>
  );
}
