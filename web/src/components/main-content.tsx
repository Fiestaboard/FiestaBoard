"use client";

import { cn } from "@/lib/utils";
import { MAX_APP_WIDTH } from "@/lib/layout-constants";
import { useSidebar } from "@/components/sidebar-context";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed, transitioning, onTransitionEnd } = useSidebar();

  return (
    <main
      className={cn(
        "h-screen flex flex-col pt-[72px] lg:pt-0 overflow-hidden w-full mx-auto sidebar-transition",
        collapsed ? "lg:pl-[76px]" : "lg:pl-[268px]",
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
