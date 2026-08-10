"use client";

import { useCurrentBoard } from "@/components/current-board-context";
import { getEffectiveBoardColor, useBoardSettings } from "@/hooks/use-board";

/**
 * The board color to preview a plugin against: the board the user is currently
 * managing, falling back to the effective color from board settings.
 *
 * Lives in its own module rather than `use-board` because
 * `current-board-context` imports from there — joining the two in `use-board`
 * would close an import cycle.
 */
export function useEffectiveBoardColor(): "black" | "white" {
  const { currentBoard } = useCurrentBoard();
  const { data: boardSettings } = useBoardSettings();
  return currentBoard?.board_color ?? getEffectiveBoardColor(boardSettings);
}
