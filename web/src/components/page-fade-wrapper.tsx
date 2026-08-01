"use client";

import { FadeContent } from "@fiestaboard/ui";

import { usePathname } from "@/hooks/use-router";

export function PageFadeWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <FadeContent key={pathname} duration={0.4} translateY={12} className="flex-1 min-h-0 flex flex-col">
      {children}
    </FadeContent>
  );
}
