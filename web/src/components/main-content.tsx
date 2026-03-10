"use client";

import { cn } from "@/lib/utils";
import { useSidebar } from "@/components/sidebar-context";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed, transitioning, onTransitionEnd } = useSidebar();

  return (
    <main
      className={cn(
        "min-h-screen pt-[72px] lg:pt-0 overflow-x-hidden w-full max-w-full sidebar-transition",
        collapsed ? "lg:pl-[76px]" : "lg:pl-[268px]",
        transitioning && "is-transitioning"
      )}
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
