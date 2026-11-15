"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/**
 * Which hub this browser is talking to, for the hub card at the head of
 * Settings and the hub line at the foot of the More drawer (07a `308:36070`,
 * 07e `320:7936`): "fiestapi.local · Online · FiestaBoard 11.1.0".
 *
 * `online` is true once the hub has answered, `false` once it has failed to,
 * and `null` before either: a state is only claimed when it is known, so the
 * line never says Online for a hub it has not heard from. The per-display
 * health and the Remote state are slice 2.3's (H12, BoardSelector `status`).
 */
export interface HubIdentity {
  /** The household's name for the hub ("Maya's FiestaPi"), or null when unset. */
  name: string | null;
  /** The address this browser reached it at. */
  host: string;
  version: string | null;
  online: boolean | null;
}

export function useHubIdentity({ enabled = true }: { enabled?: boolean } = {}): HubIdentity {
  // The same cache keys InstanceNameCard and AboutDialog use, so this costs
  // no request of its own on the screens that already ask.
  const settings = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
    staleTime: 30_000,
    retry: false,
    enabled,
  });
  const version = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity,
    retry: false,
    enabled,
  });

  const name = settings.data?.general?.instance_name?.trim() || null;
  const online = version.isSuccess ? true : version.isError ? false : null;
  return {
    name,
    host: typeof window === "undefined" ? "" : window.location.hostname,
    version: version.data?.running_version ?? null,
    online,
  };
}
