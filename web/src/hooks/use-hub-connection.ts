"use client";

import type { BoardSelectorHubStatus } from "@fiestaboard/ui";
import { useCallback, useSyncExternalStore } from "react";

import { useStatus } from "@/hooks/use-board";
import { ApiError } from "@/lib/api";
import { hubLineStatus } from "@/lib/hub-identity";
import { browserHostname } from "@/lib/network-hint";

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
  /** The hub has answered or failed at least once, so its state is known. */
  hubKnown: boolean;
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
  return {
    deviceOnline,
    hubReachable,
    hubKnown: dataUpdatedAt > 0 || isError,
    lastContactAt: dataUpdatedAt > 0 ? dataUpdatedAt : null,
    retry,
  };
}

export interface HubLine {
  /** The address this page was opened at. */
  host: string;
  /** Online / Remote / Can't reach, or undefined until known. */
  status: BoardSelectorHubStatus | undefined;
}

/**
 * The hub line's host and state: the ONE source for every surface that names
 * the hub's connection (the BoardSelector line and phone pill, the More
 * drawer's foot, the Settings hub card), so they can never disagree. Every
 * caller shares the `["status"]` poll; a surface that is not shown passes
 * `enabled: false` and adds no request.
 */
export function useHubLine({ enabled = true }: { enabled?: boolean } = {}): HubLine {
  const connection = useHubConnection({ enabled });
  const host = browserHostname();
  return {
    host,
    status: hubLineStatus({
      host,
      hubReachable: connection.hubReachable,
      hubKnown: connection.hubKnown,
      deviceOnline: connection.deviceOnline,
    }),
  };
}
