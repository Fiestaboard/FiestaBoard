"use client";

import { FadeContent } from "@fiestaboard/ui";

import { usePathname } from "@/hooks/use-router";

/**
 * The section a path belongs to: its first segment ("/displays/kitchen" →
 * "/displays"). Moving within a section is the section layout's to animate
 * (SectionShell); only moving between sections is a new page.
 */
export function sectionKey(pathname: string): string {
  const first = pathname.split("/").find(Boolean);
  return first ? `/${first}` : "/";
}

export function PageFadeWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Keyed by section, not by URL: a pathname key remounted the whole route on
  // every drill-in, including the section header that is meant to hold still.
  return (
    <FadeContent key={sectionKey(pathname)} duration={0.4} translateY={12} className="flex-1 min-h-0 flex flex-col">
      {children}
    </FadeContent>
  );
}
