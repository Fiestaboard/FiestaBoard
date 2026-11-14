"use client";

import { useCallback, useSyncExternalStore } from "react";

import { useStatus } from "@/hooks/use-board";
import { ApiError } from "@/lib/api";

function subscribeOnline(onChange: () => void): () => void {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

/** Whether this device has a network, as the browser reports it. */
export function useDeviceOnline(): boolean {
  return useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  );
}

/**
 * Whether a failed request means the hub did not answer at all: the request
 * never got a response (network error, timeout), or the proxy in front of
 * the hub said the hub behind it is gone (502, 504). Any other HTTP answer —
 * a 503 while the display loop starts, a 401 — came from the hub itself.
 */
export function isNoAnswer(error: unknown): boolean {
  if (error instanceof ApiError) return error.status === 502 || error.status === 504;
  return error != null;
}

export interface HubConnection {
  /** This device has a network. */
  deviceOnline: boolean;
  /** The hub answered the last status poll (true until the first poll fails). */
  hubReachable: boolean;
  /** When the hub last answered this browser (epoch ms), or null if it never has. */
  lastContactAt: number | null;
  /** Ask the hub again now. */
  retry: () => void;
}

/**
 * This browser's connection to the hub, from the shared 15 s status poll
 * (`GET /v1/status`, `useStatus`): no new polling loop. Drives the
 * hub-unreachable and you're-offline banners and the BoardSelector hub line.
 * `enabled: false` (a chromeless screen) makes no request.
 */
export function useHubConnection({ enabled = true }: { enabled?: boolean } = {}): HubConnection {
  const deviceOnline = useDeviceOnline();
  const { error, isError, dataUpdatedAt, refetch } = useStatus({ enabled });
  const hubReachable = !(isError && isNoAnswer(error));
  const retry = useCallback(() => {
    void refetch();
  }, [refetch]);
  return { deviceOnline, hubReachable, lastContactAt: dataUpdatedAt > 0 ? dataUpdatedAt : null, retry };
}
