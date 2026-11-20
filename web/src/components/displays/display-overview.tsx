import { Box, Button, Flex, ListItem, ListRow, ListRowGroup, Stack, StatusDot, Switch, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { ChangePageDialog } from "@/components/home/change-page-dialog";
import { scheduleNextChange } from "@/components/home/home-status";
import { useBoardDetail } from "@/components/home/use-home-data";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { queryKeys, usePages } from "@/hooks/use-board";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type BoardInstance } from "@/lib/api";
import { resolveSilenceConfig } from "@/lib/silence-config";
import { isDisplayOffline } from "@/lib/status-banners";
import { utcToLocalTime } from "@/lib/timezone-utils";

export function DisplayOverview({
  board,
  onPlayback,
  onDiagnostics,
  showChangePage = true,
}: {
  board: BoardInstance;
  onPlayback: () => void;
  onDiagnostics: () => void;
  /** Off where the page or pane header already offers Change Page… (07d). */
  showChangePage?: boolean;
}) {
  const t = useTranslations("displays.fleet");
  const ts = useTranslations("generalSettings");
  const td = useTranslations("displays");
  const tc = useTranslations("common");
  const locale = useLocale();
  const displays = useDisplayBoards();
  const { data: detail } = useBoardDetail(board.id);
  const { data: pages } = usePages();
  const { data: settings } = useQuery({ queryKey: ["all-settings"], queryFn: api.getAllSettings });
  const { data: silence } = useQuery({
    queryKey: queryKeys.silenceStatus(board.id),
    queryFn: () => api.getSilenceStatus(board.id),
  });
  const health = displays.statusFor(board.id)?.health;
  const connection = isDisplayOffline(health) ? "unreachable" : health?.reachable === true ? "online" : "unknown";
  const silenceConfig = resolveSilenceConfig(settings?.silence_schedule?.config, board.id);
  const formatSilenceTime = (utc: string | undefined) => {
    const time = utc && utcToLocalTime(utc, settings?.general?.timezone ?? "UTC");
    return time
      ? new Date(`2000-01-01T${time}:00Z`).toLocaleTimeString(locale, {
          timeZone: "UTC",
          hour: "numeric",
          minute: "2-digit",
        })
      : null;
  };
  const silenceStart = formatSilenceTime(silenceConfig.start_time);
  const silenceEnd = formatSilenceTime(silenceConfig.end_time);
  const silenceRange =
    silenceConfig.enabled && silenceStart && silenceEnd
      ? `${silenceStart} – ${silenceEnd}`
      : silenceConfig.enabled === false || silence?.enabled === false
        ? tc("off")
        : t("unknown");
  const [changing, setChanging] = useState(false);
  const name = (id: string | null | undefined) => pages?.pages.find((page) => page.id === id)?.name ?? null;
  const next =
    detail?.next_change_at && Date.parse(detail.next_change_at) > Date.now()
      ? new Date(detail.next_change_at).toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" })
      : null;
  return (
    <Stack gap="3" className="mt-4">
      <Flex align="center" gap="2" wrap data-testid="display-health-summary">
        <StatusDot
          size="sm"
          status={connection === "online" ? "success" : connection === "unreachable" ? "danger" : "neutral"}
        />
        <Text as="span" size="sm" tone="muted">
          {t(connection)}
          {health?.last_connected_at && !Number.isNaN(Date.parse(health.last_connected_at))
            ? ` · ${t("lastConnected", { time: new Date(health.last_connected_at).toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" }) })}`
            : ""}
          {health?.latency_ms != null ? ` · ${health.latency_ms} ms` : ""}
        </Text>
      </Flex>
      <Box>
        <Text weight="medium">
          {td("previewTitle")} · {detail ? (name(detail.resolved_page_id) ?? tc("none")) : t("unknown")}
        </Text>
      </Box>
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
        <ListItem>
          <ListRow
            title={ts("silenceScheduleLabel")}
            meta={silenceRange}
            render={<button type="button" onClick={onPlayback} />}
            trailing={<ChevronRight className="size-4" aria-hidden="true" />}
          />
        </ListItem>
        <ListItem>
          <ListRow
            title={t("diagnostics")}
            meta={health?.latency_ms != null ? `${health.latency_ms} ms` : t("unknown")}
            render={<button type="button" aria-label={t("diagnostics")} onClick={onDiagnostics} />}
            trailing={<ChevronRight className="size-4" aria-hidden="true" />}
          />
        </ListItem>
      </ListRowGroup>
      {showChangePage && (
        <Flex justify="end">
          <Button variant="outline" size="touch" onClick={() => setChanging(true)}>
            {t("changePage")}
          </Button>
        </Flex>
      )}
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
