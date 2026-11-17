import { Box, Button, Flex, ListRow, ListRowGroup, Stack, Switch, Text } from "@fiestaboard/ui";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { ChangePageDialog } from "@/components/home/change-page-dialog";
import { scheduleNextChange } from "@/components/home/home-status";
import { useBoardDetail } from "@/components/home/use-home-data";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { usePages } from "@/hooks/use-board";
import { useLocale, useTranslations } from "@/i18n/translations";
import type { BoardInstance } from "@/lib/api";

export function DisplayOverview({
  board,
  onPlayback,
  onDiagnostics,
}: {
  board: BoardInstance;
  onPlayback: () => void;
  onDiagnostics: () => void;
}) {
  const t = useTranslations("displays.fleet");
  const ts = useTranslations("generalSettings");
  const locale = useLocale();
  const displays = useDisplayBoards();
  const { data: detail } = useBoardDetail(board.id);
  const { data: pages } = usePages();
  const [changing, setChanging] = useState(false);
  const name = (id: string | null | undefined) => pages?.pages.find((page) => page.id === id)?.name ?? null;
  const next =
    detail?.next_change_at && !Number.isNaN(Date.parse(detail.next_change_at))
      ? new Date(detail.next_change_at).toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" })
      : null;
  return (
    <Stack gap="3" className="mt-4">
      <Box>
        <Text weight="medium">{t("nextChangeLabel")}</Text>
        <Text size="sm" tone="muted">
          {next && name(detail?.next_page_id)
            ? t("nextChange", { time: next, page: name(detail?.next_page_id)! })
            : t("nothingScheduled")}
        </Text>
      </Box>
      <ListRowGroup variant="plain" size="touch">
        <ListRow
          title={t("pauseDisplay")}
          description={t("pauseHint")}
          trailing={
            <Switch
              size="touch"
              aria-label={t("pauseDisplay")}
              checked={board.paused === true}
              disabled={displays.pausePending}
              onCheckedChange={(paused) => displays.setPaused(board.id, paused)}
            />
          }
        />
        <ListRow
          title={ts("silenceScheduleLabel")}
          render={<button type="button" onClick={onPlayback} />}
          trailing={<ChevronRight className="size-4" aria-hidden="true" />}
        />
        <ListRow
          title={t("diagnostics")}
          render={<button type="button" onClick={onDiagnostics} />}
          trailing={<ChevronRight className="size-4" aria-hidden="true" />}
        />
      </ListRowGroup>
      <Flex justify="end">
        <Button variant="outline" size="touch" onClick={() => setChanging(true)}>
          {t("changePage")}
        </Button>
      </Flex>
      {changing && (
        <ChangePageDialog
          open={changing}
          onOpenChange={setChanging}
          board={board}
          isPrimary={displays.boards[0]?.id === board.id}
          scheduleEnabled={detail?.schedule_enabled ?? board.schedule_enabled ?? false}
          currentPageId={detail?.resolved_page_id}
          nextChange={scheduleNextChange(detail, new Date())}
        />
      )}
    </Stack>
  );
}
