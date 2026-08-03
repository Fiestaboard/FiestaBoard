"use client";

import { Box, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import type { CurrentPageSnapshot } from "@/lib/ai-chat-types";
import { api, type DeviceType } from "@/lib/api";

export interface InlineBoardPreviewProps {
  snapshot: CurrentPageSnapshot;
  deviceType: DeviceType;
  /** Default `"sm"` keeps the tile grid small + fixed-size (no responsive
   *  scaling) so it sits comfortably inside a chat tool-call card. */
  size?: "sm" | "md";
  className?: string;
}

/**
 * Static board preview rendered inline with an AI tool-call card.
 *
 * Goals:
 * - Show the user *what the board would look like* after the AI's edit,
 *   not just a JSON dump of template lines.
 * - Reuse the existing {@link BoardDisplay} component so styling and
 *   character-set behavior stay in lock-step with the editor preview.
 * - **Never animate.** A chat thread can have many tool calls; flipping
 *   tiles on every render in long sessions burns CPU. We pass
 *   `isLoading={false}` and a stable `message` so tiles initialize
 *   directly to their target character (BoardDisplay's flip animation
 *   only fires on `message` *changes*, not on first paint).
 *
 * Rendering pipeline:
 * 1. Hit `/templates/render` to expand variables (`{{date_time.day_of_week}}`
 *    → `MONDAY`) and apply alignment / wrap logic.
 * 2. Pass the rendered string to BoardDisplay.
 * 3. While the render call is in flight, show a skeleton-sized placeholder
 *    so the card height doesn't jump.
 *
 * TanStack Query caches by template+metadata+deviceType, so identical
 * snapshots dedupe across multiple tool calls in the same session.
 */
export function InlineBoardPreview({ snapshot, deviceType, size = "sm", className }: InlineBoardPreviewProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["inline-preview-render", deviceType, snapshot.template, snapshot.line_metadata],
    queryFn: () => api.renderTemplate(snapshot.template, snapshot.line_metadata, deviceType),
    // Renders are deterministic for a given input — keep them
    // around so quickly switching tool-call cards is instant.
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    retry: 1,
  });

  if (isError) {
    // Don't crash the chat panel if the render API hiccups — fall
    // back to a quiet hint. The card still has a useful summary.
    return (
      <Text tone="muted" className="text-[10px] italic">
        (preview unavailable)
      </Text>
    );
  }

  // Pass `null` while loading so BoardDisplay shows its empty grid
  // sized to the device. Once the render lands we hand it the final
  // string — BoardDisplay's tile components init to that target on
  // mount, so no flip animation runs.
  return (
    <Box className={className}>
      <ScaledBoardDisplay
        message={isLoading ? null : (data?.rendered ?? "")}
        deviceType={deviceType}
        size={size}
        boardType="black"
        isStatic
      />
    </Box>
  );
}
