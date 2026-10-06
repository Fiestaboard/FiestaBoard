"use client";

import type { BoardCellGrid } from "@fiestaboard/ui";
import { memo } from "react";

import { DevicePreview } from "@/components/device-preview";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { resolveCode62Glyph, useBoardCurrentMessage } from "@/hooks/use-board";
import type { BoardInstance } from "@/lib/api";
import { resolveBoardModel } from "@/lib/device-preview";

/**
 * What a display shows right now (plan D21): its last frame from the board
 * state poll, drawn as its device — an LED board as its LED matrix, a
 * split-flap board as the app's own board, at the display's true size.
 */
export const DisplayLivePreview = memo(function DisplayLivePreview({
  board,
  size = "sm",
}: {
  board: BoardInstance;
  size?: "sm" | "md";
}) {
  // A paused board is hands-off and may be unplugged: read it once, never poll.
  const paused = board.paused === true;
  const { data: state, isLoading, errorUpdateCount } = useBoardCurrentMessage(board.id, { poll: !paused });
  // The loading animation is for the first read only. A query that never
  // succeeded goes back to "pending" on every refetch, so an unreachable
  // board would replay the animation on each poll; once a read has failed,
  // it stays a still (empty) board. A paused board never animates.
  const loading = isLoading && !paused && errorUpdateCount === 0;
  const message = state?.message ?? null;
  // A rich board's frame as its cells (colour, case, icons), when it was sent with them.
  const cells = message !== null ? (state?.cells as BoardCellGrid | undefined) : undefined;
  return (
    <DevicePreview
      model={resolveBoardModel(board)}
      ledLayout={board.led_layout}
      message={message}
      cells={cells}
      size={size}
    >
      <ScaledBoardDisplay
        message={message}
        isLoading={loading}
        size={size}
        boardType={board.board_color}
        deviceType={board.device_type}
        notesWide={board.notes_wide ?? undefined}
        notesTall={board.notes_tall ?? undefined}
        gridRows={board.grid_rows ?? undefined}
        gridCols={board.grid_cols ?? undefined}
        code62Glyph={resolveCode62Glyph(board.device_type, board.code62_glyph)}
      />
    </DevicePreview>
  );
});
