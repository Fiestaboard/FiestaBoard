"use client";

import {
  type BoardCellGrid,
  Box,
  Button,
  Card,
  CardTitle,
  Flex,
  Label,
  Stack,
  StatusDot,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Monitor } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { toast } from "sonner";

import { useCurrentBoard } from "@/components/current-board-context";
import { DevicePreview } from "@/components/device-preview";
import { formatClock } from "@/components/home/home-status";
import { nudgeDisplay } from "@/components/home/use-home-data";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import Link from "@/components/smart-link";
import { resolveCode62Glyph, useBoardCurrentMessage, useStatus } from "@/hooks/use-board";
import { useHubConnection } from "@/hooks/use-hub-connection";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type BoardDetail, type BoardInstance } from "@/lib/api";
import { resolveBoardModel } from "@/lib/device-preview";
import { isDisplayOffline } from "@/lib/status-banners";

export interface HomeSupportingPaneProps {
  board: BoardInstance | undefined;
  scheduleEnabled: boolean | undefined;
  detail: BoardDetail | undefined;
  pageName: string | null;
  nameOf: (id: string | null | undefined) => string | null;
  refresh: () => void;
  leading?: ReactNode;
}

/** DD-W50: the hub owns all event prediction. Never sort recurrence rules into a web schedule. */
export function HomeSupportingPane({
  board,
  scheduleEnabled,
  detail,
  pageName,
  nameOf,
  refresh,
  leading,
}: HomeSupportingPaneProps) {
  const t = useTranslations("home.supporting");
  const locale = useLocale();
  const connection = useHubConnection();
  const sendsDisabled = !connection.deviceOnline || !connection.hubReachable;
  const undoBlocked = useRef(sendsDisabled);
  useEffect(() => {
    undoBlocked.current = sendsDisabled;
  }, [sendsDisabled]);
  const switchId = useId();
  const undoOwner = useRef<{ id: string } | null>(null);
  useEffect(() => {
    const id = board?.id ?? null;
    undoOwner.current = id ? { id } : null;
    return () => {
      undoOwner.current = null;
      if (id) toast.dismiss(`home-schedule:${id}`);
    };
  }, [board?.id]);
  const { boards, currentBoardId } = useCurrentBoard();
  const nextAt = detail?.next_change_at ? new Date(detail.next_change_at) : null;
  const hasNext = nextAt && Number.isFinite(nextAt.getTime()) && nextAt.getTime() > Date.now();
  const nextName = nameOf(detail?.next_page_id);
  const nextTitle =
    detail?.next_change_reason === "override_ends"
      ? t("resumes")
      : detail?.next_change_reason === "silence_starts"
        ? t("silenceStarts")
        : detail?.next_change_reason === "silence_ends"
          ? t("silenceEnds")
          : (nextName ?? t("changes"));
  const toggle = useMutation({
    mutationFn: ({ id }: { id: string; owner: { id: string } | null }) => api.setScheduleEnabled(true, id),
    onSuccess: (_, { id, owner }) => {
      refresh();
      if (!undoBlocked.current) nudgeDisplay(id);
      // Navigation or another display ends this Home action's Undo lifetime.
      if (undoOwner.current !== owner) return;
      toast.success(t("enabled"), {
        id: `home-schedule:${id}`,
        duration: 10000,
        action: {
          label: t("undo"),
          onClick: async () => {
            try {
              if (undoBlocked.current || undoOwner.current !== owner) return;
              const current = await api.getBoardDetail(id);
              if (!current.schedule_enabled || undoBlocked.current || undoOwner.current !== owner) return;
              await api.setScheduleEnabled(false, id);
              refresh();
              if (!undoBlocked.current) nudgeDisplay(id);
            } catch {
              toast.error(t("failed"));
            }
          },
        },
      });
    },
    onError: () => toast.error(t("failed")),
  });
  const others = boards.filter((b) => b.id !== (board?.id ?? currentBoardId));
  return (
    <Box data-testid="home-supporting-pane" className="grid min-w-0 gap-4 md:grid-cols-2 lg:grid-cols-1 content-start">
      {leading}
      <Card className="gap-3 p-4 md:p-5 min-w-0">
        {scheduleEnabled === false ? (
          <>
            <CardTitle className="text-sm font-semibold">{t("manualTitle")}</CardTitle>
            <Text size="sm" tone="muted">
              {pageName ? t("manualBody", { page: pageName }) : t("manualEmpty")}
            </Text>
            <Flex align="center" justify="between" className="min-h-11 gap-3">
              <Label htmlFor={switchId}>{t("scheduleMode")}</Label>
              <Switch
                id={switchId}
                size="touch"
                checked={false}
                disabled={sendsDisabled || !board || toggle.isPending}
                onCheckedChange={() => {
                  if (board && !sendsDisabled) toggle.mutate({ id: board.id, owner: undoOwner.current });
                }}
              />
            </Flex>
          </>
        ) : (
          <>
            <CardTitle className="text-sm font-semibold">
              <Text as="span" className="md:hidden">
                {t("upNext")}
              </Text>
              <Text as="span" className="hidden md:inline">
                {board?.name ? t("upNextDisplay", { display: board.name }) : t("upNext")}
              </Text>
            </CardTitle>
            {hasNext ? (
              <Flex gap="3" align="start" data-testid="home-next-event">
                <time
                  dateTime={nextAt.toISOString()}
                  className="w-[70px] md:w-16 shrink-0 font-mono text-xs text-brand pt-0.5"
                >
                  {formatClock(nextAt, locale)}
                </time>
                <Stack gap="0.5" className="min-w-0">
                  <Text size="sm" className="font-medium">
                    {nextTitle}
                  </Text>
                  <Text size="xs" tone="muted">
                    {detail?.next_change_reason === "override_ends"
                      ? (nextName ?? t("scheduleMode"))
                      : nextName && nextName !== nextTitle
                        ? nextName
                        : t("scheduleMode")}
                  </Text>
                </Stack>
              </Flex>
            ) : (
              <Text size="sm" tone="muted">
                {t("empty")}
              </Text>
            )}
          </>
        )}
        <Button variant="ghost" size="sm" asChild className="self-start">
          <Link href="/schedule">{t("viewSchedule")}</Link>
        </Button>
      </Card>
      {others.length > 0 && (
        <Card className="hidden md:flex gap-3 p-5 min-w-0">
          <CardTitle className="text-sm font-semibold">{t("otherDisplays")}</CardTitle>
          {others.map((other) => (
            <OtherDisplayRow key={other.id} board={other} nameOf={nameOf} />
          ))}
          <Button variant="ghost" size="sm" asChild className="self-start gap-1.5">
            <Link href="/displays">
              <Monitor className="size-4" aria-hidden="true" />
              {t("allDisplays")}
            </Link>
          </Button>
        </Card>
      )}
    </Box>
  );
}

function OtherDisplayRow({ board, nameOf }: { board: BoardInstance; nameOf: HomeSupportingPaneProps["nameOf"] }) {
  const t = useTranslations("home.supporting");
  const { setCurrentBoardId } = useCurrentBoard();
  const { data: state } = useBoardCurrentMessage(board.id, { poll: !board.paused });
  const { data: status } = useStatus();
  const { data: active } = useQuery({
    queryKey: ["schedules", "active", board.id],
    queryFn: () => api.getActiveSchedule(board.id),
    refetchInterval: 60000,
  });
  const offline = isDisplayOffline(status?.boards?.[board.id]?.health);
  const mode = active?.temporary_override?.active
    ? t("overrideMode")
    : active?.schedule_enabled === true
      ? t("scheduleMode")
      : active?.schedule_enabled === false
        ? t("manualMode")
        : t("unknown");
  const title = nameOf(active?.temporary_override?.active ? active.temporary_override.page_id : active?.page_id);
  return (
    <Button
      variant="ghost"
      onClick={() => setCurrentBoardId(board.id)}
      className="h-auto w-full justify-start whitespace-normal px-0 gap-3 text-left"
      aria-label={t("selectDisplay", { display: board.name })}
    >
      <Box className={offline ? "w-20 shrink-0 opacity-60" : "w-20 shrink-0"} aria-hidden="true">
        <DevicePreview
          model={resolveBoardModel(board)}
          ledLayout={board.led_layout}
          message={state?.message}
          cells={state?.cells as BoardCellGrid | undefined}
          layers={state?.layers}
          size="sm"
        >
          <ScaledBoardDisplay
            thumbnail
            isStatic
            message={state?.message ?? null}
            size="sm"
            boardType={board.board_color}
            deviceType={board.device_type}
            notesWide={board.notes_wide ?? undefined}
            notesTall={board.notes_tall ?? undefined}
            gridRows={board.grid_rows ?? undefined}
            gridCols={board.grid_cols ?? undefined}
            code62Glyph={resolveCode62Glyph(board.device_type, board.code62_glyph)}
          />
        </DevicePreview>
      </Box>
      <Stack gap="1" className="min-w-0">
        <Flex gap="1.5" align="center">
          <StatusDot
            status={offline ? "danger" : status?.boards?.[board.id]?.health?.reachable ? "success" : "neutral"}
            size="sm"
          />
          <Text as="span" size="sm" className="font-medium break-words">
            {board.name}
          </Text>
        </Flex>
        <Text as="span" size="xs" tone="muted">
          {offline ? t("offline") : title ? `${mode} · ${title}` : mode}
        </Text>
      </Stack>
    </Button>
  );
}
