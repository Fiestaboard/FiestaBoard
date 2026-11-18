import { PageCard, PageSection } from "@fiestaboard/ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/** A single Settings panel, using the shared card surface and section spacing. */
export function SettingsPanel(props: ComponentProps<typeof PageSection>) {
  return (
    <PageCard>
      <PageSection {...props} className={cn("p-5", props.className)} />
    </PageCard>
  );
}
