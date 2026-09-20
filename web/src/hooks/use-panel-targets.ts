import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api } from "@/lib/api";
import type { PanelTarget } from "@/lib/panel-page-fit";
import { panelTargets } from "@/lib/panel-page-fit";

/** Shared with DisplaySettings and FiestaPanelSettings, so one fetch serves all. */
export const PANELS_QUERY_KEY = ["panels"] as const;

/**
 * The panels a page can be sized to.
 *
 * Panels change rarely (creating one is a deliberate act in Settings), so this
 * is happy to serve a cached list to the page list and the editor rather than
 * refetch per card. An install with no panels gets an empty array and every
 * caller renders exactly as it did before panels existed.
 */
export function usePanelTargets(): PanelTarget[] {
  const { data } = useQuery({
    queryKey: PANELS_QUERY_KEY,
    queryFn: () => api.listPanels(),
    staleTime: 60_000,
  });
  return useMemo(() => panelTargets(data?.panels), [data?.panels]);
}
