"use client";

import { Stack, StatusBanner, StatusBannerAction } from "@fiestaboard/ui";

import { useCurrentBoard } from "@/components/current-board-context";
import Link from "@/components/smart-link";
import { useStatus } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";

/**
 * Dashboard callout for boards that failed to initialize (issue #1829).
 *
 * The backend records why each board has no client (issue #1749) and exposes
 * it as `GET /status` → `boards[<id>].error`; until now nothing in the UI
 * read it, so a board dark from a bad credential looked identical to a
 * healthy one. One alert per failed board — a failed board is often NOT the
 * currently selected one, so this reads the whole fleet rather than scoping
 * to the current board. Rides the shared 15s status poll (useStatus); no new
 * polling loop.
 *
 * A `StatusBanner kind="init-error"` (07a `298:2280` "Couldn't start …"), with
 * Display settings as its one fix.
 */
export function BoardInitErrorBanner() {
  const t = useTranslations("statusBanners");
  const { data: status } = useStatus();
  const { boards } = useCurrentBoard();

  const failedBoards = Object.entries(status?.boards ?? {}).flatMap(([id, boardStatus]) =>
    boardStatus.error ? [{ id, error: boardStatus.error, name: boards.find((b) => b.id === id)?.name ?? "" }] : [],
  );

  if (failedBoards.length === 0) return null;

  return (
    <Stack gap="2" data-testid="board-init-error-banner">
      {failedBoards.map((board) => (
        <StatusBanner
          key={board.id}
          kind="init-error"
          title={board.name ? t("initErrorTitle", { boardName: board.name }) : t("initErrorTitleUnnamed")}
          description={board.error}
          action={
            <StatusBannerAction asChild>
              <Link href={`/displays/${encodeURIComponent(board.id)}?section=settings`}>{t("displaySettings")}</Link>
            </StatusBannerAction>
          }
        />
      ))}
    </Stack>
  );
}
