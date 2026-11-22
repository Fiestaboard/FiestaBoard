import { Heading } from "@fiestaboard/ui";
import type { ReactNode } from "react";

/**
 * A settings section's mono caps label (07d `324:40267`: ACCOUNT, CALENDARS,
 * UNLOCKS 3 VARIABLES), as a heading so the sections stay navigable. FiestaUI
 * has no overline type yet; this is the one place the app composes it.
 */
export const SECTION_LABEL_CLASS = "font-mono text-xs font-medium uppercase tracking-wide text-muted-foreground";

export function SectionLabel({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <Heading id={id} level={3} size="sm" className={SECTION_LABEL_CLASS}>
      {children}
    </Heading>
  );
}
