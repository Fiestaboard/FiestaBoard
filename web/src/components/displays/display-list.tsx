import {
  Badge,
  Box,
  Card,
  Flex,
  Heading,
  ListItem,
  ListRow,
  ListRowGroup,
  Stack,
  StatusDot,
  Text,
} from "@fiestaboard/ui";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { BoardSizeIndicator } from "@/components/board-size-indicator";
import { BOARD_DETAIL_KEY } from "@/components/home/use-home-data";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { isVirtualBoard } from "@/components/settings/output-boards";
import Link from "@/components/smart-link";
import { useBelowRail } from "@/hooks/use-below-rail";
import { queryKeys, usePages } from "@/hooks/use-board";
import { useMediaQuery } from "@/hooks/use-media-query";
import { PANELS_QUERY_KEY } from "@/hooks/use-panel-targets";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, sessionsApi } from "@/lib/api";
import { isDisplayOffline, panelViewer } from "@/lib/status-banners";

import { DisplayDetail } from "./display-detail";

/** Fleet facts stay hub-sourced; an absent health report never means Online. */
export function DisplayList({
  outputName,
}: {
  outputName: (board: ReturnType<typeof useDisplayBoards>["boards"][number]) => string;
}) {
  const t = useTranslations("displays.fleet");
  const td = useTranslations("displays");
  const tn = useTranslations("home.nowShowing");
  const locale = useLocale();
  const phone = useBelowRail();
  const compact = useMediaQuery("(max-width: 1023.98px)");
  const displays = useDisplayBoards();
  const [selection, setSelection] = useState<string | null>(null);
  const selected = displays.boards.find((board) => board.id === selection) ?? displays.boards[0];
  const { data: pages } = usePages();
  const states = useQueries({
    queries: displays.boards.map((board) => ({
      queryKey: queryKeys.boardCurrentMessage(board.id),
      queryFn: () => api.getBoardCurrentMessage(board.id),
      refetchInterval: board.paused ? (false as const) : 30_000,
    })),
  });
  const details = useQueries({
    queries: displays.boards.map((board) => ({
      queryKey: [BOARD_DETAIL_KEY, board.id],
      queryFn: () => api.getBoardDetail(board.id),
      refetchInterval: 60_000,
    })),
  });
  const { data: panels } = useQuery({ queryKey: PANELS_QUERY_KEY, queryFn: () => api.listPanels() });
  const { data: sessions } = useQuery({
    queryKey: ["auth-sessions", "viewers"],
    queryFn: () => sessionsApi.listSessions(),
    enabled: displays.boards.some(isVirtualBoard),
    retry: false,
    refetchInterval: 60_000,
  });
  const pageName = (id: string | null | undefined) => pages?.pages.find((page) => page.id === id)?.name;
  const clock = (iso: string | null | undefined) => {
    if (!iso || Number.isNaN(Date.parse(iso))) return null;
    return new Date(iso).toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
  };
  const rows = displays.boards.map((board, index) => {
    const status = displays.statusFor(board.id);
    const health = status?.health;
    const state = states[index].data;
    const detail = details[index].data;
    const panel = panels?.panels.find((item) => item.board_id === board.id);
    const viewer =
      panel && !panel.is_display && sessions ? panelViewer(panel.id, sessions.sessions, Date.now()) : undefined;
    const offline = isDisplayOffline(health);
    const outOfSync =
      Boolean(state?.overwritten_at) ||
      (state?.characters != null &&
        state?.expected_characters != null &&
        JSON.stringify(state.characters) !== JSON.stringify(state.expected_characters));
    const kind =
      status?.error || status?.configured === false
        ? "notConfigured"
        : offline
          ? "unreachable"
          : outOfSync
            ? "outOfSync"
            : viewer?.showing === false
              ? "noViewer"
              : board.paused || status?.paused
                ? "paused"
                : health?.reachable === true || status?.output_status?.state === "connected" || viewer?.showing === true
                  ? "online"
                  : "unknown";
    const group = ["notConfigured", "unreachable", "outOfSync", "noViewer"].includes(kind)
      ? "attention"
      : kind === "online"
        ? "online"
        : "other";
    const last = clock(health?.last_connected_at);
    const until = clock(detail?.next_change_at);
    const next = pageName(detail?.next_page_id);
    const healthCause =
      kind === "unreachable" && last
        ? t("lastConnected", { time: last })
        : kind === "outOfSync" && clock(health?.last_update_at)
          ? t("lastUpdate", { time: clock(health?.last_update_at)! })
          : kind === "noViewer"
            ? t("noViewerHint")
            : undefined;
    const current = pageName(detail?.resolved_page_id ?? status?.active_page_id);
    const cause = healthCause ?? (until && next ? t("nextChange", { time: until, page: next }) : current);
    const compactCause = healthCause ?? (until && next ? t("nextCompact", { page: next }) : current);
    const override =
      detail?.override_expires_at && Date.parse(detail.override_expires_at) > Date.now()
        ? clock(detail.override_expires_at)
        : null;
    return { board, kind, group, cause, compactCause, override };
  });
  return (
    <Box
      className="grid min-w-0 gap-4 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)] xl:grid-cols-[minmax(0,1.54fr)_minmax(0,1fr)]"
      data-testid="display-list-detail"
    >
      <Stack gap="3" className="min-w-0">
        {(["attention", "online", "other"] as const).map((group) => {
          const items = rows.filter((row) => row.group === group);
          if (!items.length) return null;
          return (
            <Stack key={group} gap="2">
              <Heading level={2} size="sm" className="font-mono uppercase text-muted-foreground">
                {t(group)}
              </Heading>
              <ListRowGroup aria-label={t(group)}>
                {items.map(({ board, kind, cause, compactCause, override }) => (
                  <ListItem key={board.id}>
                    <ListRow
                      data-testid="display-card"
                      data-section-item={board.id}
                      selected={!phone && selected?.id === board.id}
                      size="touch"
                      layout={compact ? "inline" : "auto"}
                      className={
                        compact
                          ? "[&_[data-slot=list-row-title]]:text-sm [&_[data-slot=list-row-description]]:text-xs"
                          : undefined
                      }
                      render={
                        <Link
                          href={`/displays/${encodeURIComponent(board.id)}`}
                          onClick={(event) => {
                            if (phone || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                            event.preventDefault();
                            setSelection(board.id);
                          }}
                        />
                      }
                      leading={
                        <StatusDot
                          size="sm"
                          status={
                            kind === "online"
                              ? "success"
                              : kind === "noViewer"
                                ? "warning"
                                : group === "attention"
                                  ? "danger"
                                  : "neutral"
                          }
                        />
                      }
                      title={board.name || td("unnamed")}
                      description={
                        <>
                          <Text as="span" size="sm" tone="muted" className={compact ? "sr-only" : undefined}>
                            <Text as="span" data-testid="display-output" size="xs">
                              {outputName(board)}
                            </Text>
                            {" · "}
                            <BoardSizeIndicator
                              deviceType={board.device_type}
                              notesWide={board.notes_wide}
                              notesTall={board.notes_tall}
                              gridRows={board.grid_rows}
                              gridCols={board.grid_cols}
                            />
                            {cause && " · "}
                          </Text>
                          {cause && (
                            <Text
                              as="span"
                              size={compact ? "xs" : "sm"}
                              tone="muted"
                              className={compact ? "block truncate" : undefined}
                              title={cause}
                            >
                              {compact ? compactCause : cause}
                            </Text>
                          )}
                        </>
                      }
                      meta={
                        <Flex align="center" gap="2" wrap>
                          <Text
                            as="span"
                            size="sm"
                            className={
                              compact && override && kind === "online"
                                ? "sr-only"
                                : group === "attention"
                                  ? kind === "noViewer"
                                    ? "text-foreground"
                                    : "text-destructive"
                                  : "text-muted-foreground"
                            }
                          >
                            {t(kind)}
                          </Text>
                          {override && (
                            <Badge
                              variant="outline"
                              aria-label={compact ? t("overrideUntil", { time: override }) : undefined}
                            >
                              {compact ? tn("modeOverride") : t("overrideUntil", { time: override })}
                            </Badge>
                          )}
                        </Flex>
                      }
                      trailing={<ChevronRight aria-hidden="true" className="size-4" />}
                    />
                  </ListItem>
                ))}
              </ListRowGroup>
            </Stack>
          );
        })}
      </Stack>
      {!phone && selected && (
        <Card className="min-w-0 gap-3 self-start p-4" data-testid="display-detail-pane">
          <Heading level={2} size="lg">
            {selected.name || td("unnamed")}
          </Heading>
          <DisplayDetail key={selected.id} boardId={selected.id} embedded />
        </Card>
      )}
    </Box>
  );
}
