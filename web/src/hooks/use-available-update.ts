import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/**
 * The version waiting to be installed, or `null` when there is nothing this
 * install can act on.
 *
 * One rule for the rail chrome, so the account trigger's dot, the hamburger's
 * dot and the menu's "Update to X.Y.Z" item cannot disagree: an update counts
 * only when FiestaBoard can apply it. When an external supervisor owns updates
 * (the Home Assistant add-on), pointing at one would be an offer the app
 * cannot honour — see `useIsManagedExternally`.
 *
 * Same keys and stale times as every other consumer of these two endpoints
 * (AboutDialog, SystemUpdate), so a second caller shares the cached responses
 * rather than issuing extra requests.
 *
 * `enabled` exists for chrome that renders on routes it then hides on — the
 * TV viewer must not fire authenticated requests it has no use for.
 */
export function useAvailableUpdate({ enabled = true }: { enabled?: boolean } = {}): string | null {
  const { data: updateStatus } = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
    enabled,
  });
  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60,
    retry: false,
    enabled,
  });

  return !updateStatus?.managed_externally && updateCheck?.update_available ? updateCheck.latest_version : null;
}
