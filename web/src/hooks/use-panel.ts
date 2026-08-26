"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export const panelKeys = {
  config: (panelId: string) => ["panel", panelId] as const,
  frame: (panelId: string) => ["panel-frame", panelId] as const,
};

/** Default cadences: config changes rarely; frames drive the display. */
export const PANEL_CONFIG_INTERVAL_MS = 10_000;
export const PANEL_FRAME_INTERVAL_MS = 2_000;

/**
 * The panel's public viewer config (no auth). Polled so edits made in the
 * app reach a hosted TV within seconds.
 */
export function usePanelConfig(panelId: string, refetchInterval: number = PANEL_CONFIG_INTERVAL_MS) {
  return useQuery({
    queryKey: panelKeys.config(panelId),
    queryFn: () => api.getPanel(panelId),
    refetchInterval,
    // The poll interval IS the retry policy — retrying inside a 2–10s
    // cadence just multiplies requests during an outage.
    retry: false,
    staleTime: refetchInterval / 2,
  });
}

/** The virtual board's current frame (no auth), polled at ~2s. */
export function usePanelFrame(panelId: string, refetchInterval: number = PANEL_FRAME_INTERVAL_MS) {
  return useQuery({
    queryKey: panelKeys.frame(panelId),
    queryFn: () => api.getPanelFrame(panelId),
    refetchInterval,
    retry: false,
    staleTime: refetchInterval / 2,
  });
}
