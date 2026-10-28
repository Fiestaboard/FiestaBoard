"use client";

import { FadeContent } from "@fiestaboard/ui";

import { usePathname } from "@/hooks/use-router";

/** Sections whose layout (SectionShell) animates its own list ↔ item moves. */
const SECTIONS = new Set(["displays", "integrations", "pages"]);

/**
 * What the app-level fade is keyed on. Inside a section, its root
 * ("/displays/kitchen" → "/displays"): moving between the list and an item is
 * the section's to animate, and remounting would undo it. Everywhere else the
 * whole path, as before — /panel/:id and friends may seed state from the URL
 * on mount and rely on a fresh mount per URL.
 */
export function sectionKey(pathname: string): string {
  const first = pathname.split("/").find(Boolean);
  return first && SECTIONS.has(first) ? `/${first}` : pathname;
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
