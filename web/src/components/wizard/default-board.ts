import type { BoardInstance } from "@/lib/api";
import { api } from "@/lib/api";

/**
 * A fresh install's board store holds one untouched placeholder: a Vestaboard
 * named "My Board" with no connection detail at all. The Vestaboard path of
 * the setup wizard fills it in; the TV and output-plugin paths create a board
 * of their own, after which the placeholder would linger as the primary board
 * — the one the welcome message and the dashboard reach for — and never work.
 */
export function isUntouchedPlaceholder(board: BoardInstance): boolean {
  const isVestaboard = !board.output || board.output === "vestaboard";
  return (
    isVestaboard &&
    board.api_mode !== "virtual" &&
    board.device_type !== "panel" &&
    !board.host &&
    !board.local_api_key &&
    !board.cloud_key &&
    !board.note_array_token &&
    (board.tiles ?? []).length === 0
  );
}

/**
 * After the wizard created board `keptId`, remove the placeholder — only when
 * it is the one other board, so nothing a user set up is ever touched.
 * Best effort: a leftover placeholder is harmless and can be deleted in
 * Settings.
 */
export async function removeUntouchedPlaceholder(keptId: string): Promise<void> {
  try {
    const { boards } = await api.getBoardSettings();
    const others = boards.filter((board) => board.id !== keptId);
    if (others.length === 1 && isUntouchedPlaceholder(others[0])) {
      await api.removeBoard(others[0].id);
    }
  } catch {
    // Leave it: Settings → Boards can delete it.
  }
}
