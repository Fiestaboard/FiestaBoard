"use client";

import { Box, Flex, PageSection, Skeleton, Text } from "@fiestaboard/ui";
import { Monitor } from "lucide-react";

import { BoardEditor, BoardStatusBadges, BoardSummary, useDisplayBoards } from "@/components/settings/display-settings";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";

/**
 * One display's settings (plan D21): its name, shape and state, then
 * everything {@link BoardEditor} edits.
 */
export function DisplayEditor({ boardId, onRemoved }: { boardId: string; onRemoved?: () => void }) {
  const displays = useDisplayBoards();
  const t = useTranslations("displaySettings");
  const td = useTranslations("displays");
  const board = displays.boards.find((b) => b.id === boardId);

  if (displays.isLoading) {
    return (
      <PageSection>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="mt-4 h-20 w-full" />
      </PageSection>
    );
  }
  if (!board) {
    return (
      <PageSection>
        <Text tone="muted" data-testid="display-not-found">
          {td("notFound")}
        </Text>
      </PageSection>
    );
  }

  return (
    <PageSection icon={<Monitor />} title={td("settingsTitle")} {...anchorProps("settings.boards")}>
      <Box
        data-testid="board-card"
        data-paused={board.paused ? "true" : undefined}
        {...anchorProps(`settings.board.${board.id}`)}
        className={`rounded-lg border ${board.paused ? "border-amber-500/60 bg-amber-500/5" : ""}`}
      >
        <Flex align="center" gap="3" className="border-b p-3">
          <Box className="min-w-0 flex-1">
            <Text weight="medium" className="truncate">
              {board.name || t("unnamedBoard")}
            </Text>
            <BoardSummary board={board} />
          </Box>
          <BoardStatusBadges board={board} status={displays.statusFor(board.id)} />
        </Flex>
        <Box className="px-4 pb-4 pt-3">
          <BoardEditor board={board} displays={displays} onRemoved={onRemoved} />
        </Box>
      </Box>
    </PageSection>
  );
}
