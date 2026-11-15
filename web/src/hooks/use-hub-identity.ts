"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/**
 * Which hub this browser is talking to, for the hub card at the head of
 * Settings and the hub line at the foot of the More drawer (07a `308:36070`,
 * 07e `320:7936`): "fiestapi.local · Online · FiestaBoard 11.1.0".
 *
 * The connection state (Online / Remote / Can't reach) is NOT here: it comes
 * from `useHubLine` (slice 2.3), the one source every hub line reads.
 */
export interface HubIdentity {
  /** The household's name for the hub ("Maya's FiestaPi"), or null when unset. */
  name: string | null;
  /** The address this browser reached it at. */
  host: string;
  version: string | null;
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
  return {
    name,
    host: typeof window === "undefined" ? "" : window.location.hostname,
    version: version.data?.running_version ?? null,
  };
}
