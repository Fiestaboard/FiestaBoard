import { useQuery } from "@tanstack/react-query";

import { isVirtualBoard } from "@/components/settings/output-boards";
import { useStatus } from "@/hooks/use-board";
import { PANELS_QUERY_KEY } from "@/hooks/use-panel-targets";
import { api, type BoardInstance, sessionsApi } from "@/lib/api";
import { isDisplayOffline, panelViewer } from "@/lib/status-banners";

/** Shared with the status banners, so the shell adds no request of its own. */
export const VIEWER_SESSIONS_QUERY_KEY = ["auth-sessions", "viewers"] as const;

/**
 * The displays that "need a look" (BB-A-10), by the rules the Displays list
 * groups them with: a client that failed to start or is not configured, a
 * display the hub cannot reach, or a FiestaPanel no signed-in TV is showing.
 * The header switcher marks them, so it never calls a display fine while
 * Home and Displays say otherwise. Reads the shared status poll; panels and
 * viewer sessions are asked for only when a FiestaPanel exists.
 */
export function useDisplaysNeedingALook(boards: ReadonlyArray<BoardInstance>, { enabled = true } = {}): Set<string> {
  const { data: status } = useStatus({ enabled });
  const anyPanel = enabled && boards.some(isVirtualBoard);
  const { data: panels } = useQuery({
    queryKey: PANELS_QUERY_KEY,
    queryFn: () => api.listPanels(),
    staleTime: 60_000,
    enabled: anyPanel,
  });
  const { data: sessions } = useQuery({
    queryKey: VIEWER_SESSIONS_QUERY_KEY,
    queryFn: () => sessionsApi.listSessions(),
    enabled: anyPanel,
    // Sign-in off answers 401: viewers are unknown, so nothing is flagged.
    retry: false,
    refetchInterval: 60_000,
  });
  const flagged = new Set<string>();
  for (const board of boards) {
    const boardStatus = status?.boards?.[board.id];
    if (boardStatus?.error || boardStatus?.configured === false || isDisplayOffline(boardStatus?.health)) {
      flagged.add(board.id);
      continue;
    }
    const panel = panels?.panels.find((item) => item.board_id === board.id);
    if (panel && !panel.is_display && sessions && !panelViewer(panel.id, sessions.sessions, Date.now()).showing) {
      flagged.add(board.id);
    }
  }
  return flagged;
}
