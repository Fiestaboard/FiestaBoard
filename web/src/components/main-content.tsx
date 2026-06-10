"use client";

import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { useSidebar } from "@/components/sidebar-context";
import { usePathname } from "@/hooks/use-router";
import { MAX_APP_WIDTH } from "@/lib/layout-constants";
import { cn } from "@/lib/utils";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed, transitioning, onTransitionEnd } = useSidebar();
  const { isOpen: aiPanelOpen } = useGlobalAiPanel();
  const pathname = usePathname();
  // Auth screens render edge-to-edge with no sidebar — drop the chrome
  // padding so the login form centers in the actual viewport.
  const isAuthScreen = pathname.startsWith("/login");

  return (
    <main
      id="main-content"
      className={cn(
        "min-h-dvh flex flex-col w-full mx-auto",
        !isAuthScreen && "pt-[72px] lg:pt-0 sidebar-transition",
        !isAuthScreen && (collapsed ? "lg:pl-[76px]" : "lg:pl-[268px]"),
        !isAuthScreen && (aiPanelOpen ? "lg:pr-[384px]" : "lg:pr-0"),
        !isAuthScreen && transitioning && "is-transitioning",
      )}
      style={{ maxWidth: isAuthScreen ? undefined : MAX_APP_WIDTH }}
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
