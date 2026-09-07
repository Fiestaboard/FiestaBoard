import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/**
 * True when FiestaBoard's lifecycle is owned by an external supervisor — the
 * Home Assistant add-on — which ships its own update flow through the
 * Supervisor's add-on store.
 *
 * FiestaBoard cannot update itself in that deployment, and the Supervisor
 * already surfaces its own "update available" notice, so every in-app update
 * notification (sidebar badge, System banner, About pill, check-for-updates
 * card and toasts) must be hidden. This reads the server-side
 * `managed_externally` flag off `/system/update/status`.
 *
 * Defaults to `false` while loading or on error, so non-HA installs (Docker
 * Compose, Pi image) keep every existing update affordance.
 */
export function useIsManagedExternally(): boolean {
  const { data } = useQuery({
    // Same key as every other consumer of /system/update/status, so this
    // shares the cached response rather than issuing an extra request.
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
  });
  return data?.managed_externally ?? false;
}
