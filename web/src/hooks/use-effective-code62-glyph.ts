"use client";

import { useCurrentBoard } from "@/components/current-board-context";
import { getEffectiveCode62Glyph, resolveCode62Glyph, useBoardSettings } from "@/hooks/use-board";
import type { Code62Glyph } from "@/lib/api";

/**
 * The code-62 flap to preview against: the board the user is currently
 * managing, falling back to board settings (issue #1657).
 *
 * Sibling of `useEffectiveBoardColor`, and lives in its own module for the same
 * reason — `current-board-context` imports from `use-board`, so joining the two
 * there would close an import cycle.
 */
export function useEffectiveCode62Glyph(): Code62Glyph {
  const { currentBoard } = useCurrentBoard();
  const { data: boardSettings } = useBoardSettings();
  if (currentBoard) return resolveCode62Glyph(currentBoard.device_type, currentBoard.code62_glyph);
  return getEffectiveCode62Glyph(boardSettings);
}
