"use client";

import { Alert, AlertDescription, AlertTitle, Box, Button, Flex, Stack } from "@fiestaboard/ui";
import { AlertTriangle } from "lucide-react";

import { useCurrentBoard } from "@/components/current-board-context";
import { useStatus } from "@/hooks/use-board";
import { useRouter } from "@/hooks/use-router";
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
 */
export function BoardInitErrorBanner() {
  const t = useTranslations("home");
  const router = useRouter();
  const { data: status } = useStatus();
  const { boards } = useCurrentBoard();

  const failedBoards = Object.entries(status?.boards ?? {}).flatMap(([id, boardStatus]) =>
    boardStatus.error ? [{ id, error: boardStatus.error, name: boards.find((b) => b.id === id)?.name ?? "" }] : [],
  );

  if (failedBoards.length === 0) return null;

  return (
    <Stack gap="2" className="mb-6" data-testid="board-init-error-banner">
      {failedBoards.map((board) => (
        <Alert
          key={board.id}
          variant="destructive"
          className="flex flex-col sm:flex-row sm:items-center sm:gap-4 [&>svg]:static [&>svg]:shrink-0 [&>svg+div]:translate-y-0 [&>svg~*]:pl-3"
        >
          <AlertTriangle className="h-4 w-4" />
          <Box className="flex-1 min-w-0">
            <AlertTitle>
              {board.name ? t("boardInitErrorTitle", { boardName: board.name }) : t("boardInitErrorTitleUnnamed")}
            </AlertTitle>
            <AlertDescription>{board.error}</AlertDescription>
          </Box>
          <Flex align="center" className="self-center shrink-0">
            <Button variant="outline" size="sm" onClick={() => router.push("/settings?section=hardware")}>
              {t("boardInitErrorOpenSettings")}
            </Button>
          </Flex>
        </Alert>
      ))}
    </Stack>
  );
}
