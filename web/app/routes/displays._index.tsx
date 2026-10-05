import {
  Box,
  Button,
  Dialog,
  Flex,
  Grid,
  PageCard,
  PageHeader,
  PageLayout,
  PageSection,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { Monitor, Pause, Play, Plus, Settings2 } from "lucide-react";
import { useState } from "react";

import { AddDisplayDialog } from "@/components/displays/add-display-dialog";
import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import { BoardStatusBadges, BoardSummary, useDisplayBoards } from "@/components/settings/display-settings";
import { useOutputs } from "@/components/settings/output-boards";
import Link from "@/components/smart-link";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { BoardInstance } from "@/lib/api";

/**
 * Displays (plan D21): every display FiestaBoard shows on — its live
 * preview, name, output and state, with a way into its settings and a
 * pause / resume — and "Add a display".
 */
export default function DisplaysPage() {
  const t = useTranslations("displays");
  const router = useRouter();
  const displays = useDisplayBoards();
  const { data: outputs } = useOutputs();
  const [adding, setAdding] = useState(false);
  const outputName = (board: BoardInstance) => {
    const id = board.output ?? "vestaboard";
    return outputs?.find((o) => o.id === id)?.name ?? id;
  };

  return (
    <PageLayout>
      <PageCard>
        <PageHeader icon={Monitor} title={t("title")} description={t("description")}>
          <Button onClick={() => setAdding(true)} data-testid="add-display">
            <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
            {t("addDisplay")}
          </Button>
        </PageHeader>

        <PageSection {...anchorProps("settings.boards")}>
          {displays.isLoading ? (
            <Grid gap="4" className="md:grid-cols-2">
              <Skeleton className="h-48 w-full" />
              <Skeleton className="h-48 w-full" />
            </Grid>
          ) : displays.boards.length === 0 ? (
            <Text tone="muted">{t("empty")}</Text>
          ) : (
            <Grid gap="4" className="md:grid-cols-2" role="list" aria-label={t("listLabel")}>
              {displays.boards.map((board) => {
                const name = board.name || t("unnamed");
                const paused = board.paused === true;
                return (
                  <Box
                    key={board.id}
                    role="listitem"
                    data-testid="display-card"
                    data-paused={paused ? "true" : undefined}
                    {...anchorProps(`displays.card.${board.id}`)}
                    className={`flex flex-col gap-3 rounded-lg border p-4 ${paused ? "border-amber-500/60 bg-amber-500/5" : ""}`}
                  >
                    <Flex justify="center" className="overflow-hidden" style={{ contain: "layout style paint" }}>
                      <DisplayLivePreview board={board} />
                    </Flex>
                    <Flex align="start" justify="between" gap="2">
                      <Stack gap="1" className="min-w-0">
                        <Text weight="medium" className="truncate">
                          {name}
                        </Text>
                        <Text size="xs" tone="muted" data-testid="display-output">
                          {outputName(board)}
                        </Text>
                        <BoardSummary board={board} />
                      </Stack>
                      <BoardStatusBadges board={board} status={displays.statusFor(board.id)} />
                    </Flex>
                    <Flex gap="2" wrap>
                      <Button asChild variant="outline" size="sm">
                        <Link
                          href={`/displays/${encodeURIComponent(board.id)}`}
                          aria-label={t("openSettingsLabel", { name })}
                        >
                          <Settings2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                          {t("openSettings")}
                        </Link>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => displays.setPaused(board.id, !paused)}
                        disabled={displays.pausePending}
                        aria-label={paused ? t("resumeLabel", { name }) : t("pauseLabel", { name })}
                      >
                        {paused ? (
                          <Play className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                        ) : (
                          <Pause className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                        )}
                        {paused ? t("resume") : t("pause")}
                      </Button>
                    </Flex>
                  </Box>
                );
              })}
            </Grid>
          )}
        </PageSection>
      </PageCard>

      <Dialog open={adding} onOpenChange={setAdding}>
        {adding && (
          <AddDisplayDialog
            onCancel={() => setAdding(false)}
            onCreated={(boardId) => {
              setAdding(false);
              router.push(`/displays/${encodeURIComponent(boardId)}`);
            }}
          />
        )}
      </Dialog>
    </PageLayout>
  );
}
