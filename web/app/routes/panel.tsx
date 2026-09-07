import { useParams } from "react-router";

import { PanelView } from "@/components/panel/panel-view";

/**
 * FiestaPanel TV viewer — a chrome-less, full-viewport split-flap display.
 *
 * This route is public (no login) and renders outside the app chrome: the
 * sidebar, wizard takeover, and login redirects are all suppressed for
 * `/panel/` paths via `@/lib/chromeless`.
 */
export default function PanelRoute() {
  const { panelId } = useParams<{ panelId: string }>();
  if (!panelId) return null;
  return <PanelView panelId={panelId} />;
}
