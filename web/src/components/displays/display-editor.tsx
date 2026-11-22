"use client";

import { Box, Button, Flex, PageSection, Skeleton, Stack, Text } from "@fiestaboard/ui";
import { Monitor, Plus } from "lucide-react";

import { useAddDisplay } from "@/components/displays/add-display-context";
import { BoardEditor, BoardStatusBadges, BoardSummary, useDisplayBoards } from "@/components/settings/display-settings";
import Link from "@/components/smart-link";
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
  const tf = useTranslations("displays.fleet");
  const openAdd = useAddDisplay();
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
    // BB-A-20: say it is gone and offer the ways forward.
    return (
      <PageSection>
        <Stack gap="4" data-testid="display-not-found">
          <Text tone="muted">{td("notFound")}</Text>
          <Flex gap="3" wrap>
            <Button asChild variant="outline">
              <Link href="/displays">{tf("back")}</Link>
            </Button>
            <Button onClick={() => openAdd()}>
              <Plus className="size-4" aria-hidden="true" />
              {td("addDisplay")}
            </Button>
          </Flex>
        </Stack>
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
