"use client";

import { useCurrentBoard } from "@/components/current-board-context";
import { getEffectiveCode62Glyph, resolveCode62Glyph, useBoardSettings } from "@/hooks/use-board";
import type { Code62Glyph } from "@/lib/api";

/**
 * The glyph a plugin preview should draw for character code 62: the board the
 * user is currently managing, falling back to the effective glyph from board
 * settings while that is still loading (issue #1666).
 *
 * The device is resolved alongside the preference, not after it — a Note is
 * heart hardware whatever a stale Flagship preference says.
 *
 * Lives beside `use-effective-board-color` rather than in `use-board` for the
 * same reason it does: `current-board-context` imports from there, and joining
 * the two would close an import cycle.
 */
export function useEffectiveCode62Glyph(): Code62Glyph {
  const { currentBoard } = useCurrentBoard();
  const { data: boardSettings } = useBoardSettings();
  if (currentBoard) return resolveCode62Glyph(currentBoard.device_type, currentBoard.code62_glyph);
  return getEffectiveCode62Glyph(boardSettings);
}
