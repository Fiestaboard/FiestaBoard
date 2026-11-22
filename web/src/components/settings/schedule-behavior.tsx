"use client";

import {
  Box,
  Flex,
  Label,
  PageSection,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { queryKeys, useCollections, usePages } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api, type BoardInstance, type BoardSettings, type SchedulesResponse } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";

/** Schedule re-enabling behavior belongs to the explicitly targeted display. */
export function ScheduleBehavior({ board, showIcon = true }: { board: BoardInstance; showIcon?: boolean }) {
  return <BoardScheduleBehavior key={board.id} board={board} showIcon={showIcon} />;
}

function BoardScheduleBehavior({ board, showIcon }: { board: BoardInstance; showIcon: boolean }) {
  const t = useTranslations("generalSettings");
  const queryClient = useQueryClient();
  const ts = useTranslations("schedule");
  const scheduleKey = ["schedules", board.id];
  const schedule = useQuery({ queryKey: scheduleKey, queryFn: () => api.getSchedules(board.id) });
  const { data: pagesData } = usePages();
  const { data: collectionsData } = useCollections();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: scheduleKey });
    queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
    queryClient.invalidateQueries({ queryKey: queryKeys.activePage() });
    queryClient.invalidateQueries({ queryKey: ["all-settings"] });
  };
  const mode = useMutation({
    mutationFn: (enabled: boolean) => api.setScheduleEnabled(enabled, board.id),
    onSuccess: (result, enabled) => {
      queryClient.setQueryData<SchedulesResponse>(
        scheduleKey,
        (previous) => previous && { ...previous, enabled: result.schedule_enabled ?? enabled },
      );
      refresh();
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const gapDefault = useMutation({
    mutationFn: (pageId: string | null) =>
      api.setDefaultPage(
        pageId,
        board.id,
        schedule.data?.default_page_edit_protocol === "schedule-default-revision-v1"
          ? schedule.data.default_page_revision
          : undefined,
      ),
    onSuccess: (result) => {
      queryClient.setQueryData<SchedulesResponse>(
        scheduleKey,
        (previous) =>
          previous && {
            ...previous,
            default_page_id: result.default_page_id,
            ...("revision" in result ? { default_page_revision: result.revision } : {}),
          },
      );
      refresh();
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const scheduleEnabled = mode.isPending ? mode.variables : (schedule.data?.enabled ?? board.schedule_enabled ?? false);
  const defaultPageId = gapDefault.isPending ? gapDefault.variables : schedule.data?.default_page_id;
  const pages = pagesData?.pages ?? [];
  const compatiblePages = pages.filter((page) => page.id === defaultPageId || pagesCompatibleWithBoard(page, board));
  const collections = (collectionsData?.collections ?? []).filter(
    (collection) =>
      collection.id === defaultPageId ||
      (collection.page_ids.length > 0 &&
        collection.page_ids.every((id) => {
          const page = pages.find((item) => item.id === id);
          return !!page && pagesCompatibleWithBoard(page, board);
        })),
  );
  const unknownDefault =
    defaultPageId &&
    !pages.some((page) => page.id === defaultPageId) &&
    !collections.some((collection) => collection.id === defaultPageId);

  const [saved, setSaved] = useState(board.schedule_defer_on_reenable ?? false);
  const [deferOnReenable, setDeferOnReenable] = useState(saved);
  if (useDepsChanged([board.schedule_defer_on_reenable])) {
    setSaved(board.schedule_defer_on_reenable ?? false);
    setDeferOnReenable(board.schedule_defer_on_reenable ?? false);
  }

  const updateMutation = useMutation({
    mutationFn: (defer: boolean) => api.setScheduleSettings({ defer_on_reenable: defer }, board.id),
    onSuccess: (result, defer) => {
      const persisted = result.defer_on_reenable ?? defer;
      setSaved(persisted);
      setDeferOnReenable(persisted);
      queryClient.setQueryData<BoardSettings>(
        queryKeys.boardSettings,
        (previous) =>
          previous && {
            ...previous,
            boards: previous.boards.map((item) =>
              item.id === board.id ? { ...item, schedule_defer_on_reenable: persisted } : item,
            ),
          },
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    },
    onError: (error: Error) => {
      setDeferOnReenable(saved);
      toast.error(error.message);
    },
  });

  return (
    <PageSection
      icon={showIcon ? <CalendarClock /> : undefined}
      title={t("scheduleBehaviorTitle")}
      description={t("scheduleBehaviorDescription")}
      {...anchorProps("settings.schedule_behavior")}
    >
      <Stack gap="4">
        {schedule.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : schedule.isError ? (
          <Text role="alert" tone="destructive">
            {schedule.error.message}
          </Text>
        ) : (
          <>
            <Flex align="center" justify="between" gap="3">
              <Label htmlFor={`schedule-mode-${board.id}`}>{ts("scheduleMode")}</Label>
              <Switch
                id={`schedule-mode-${board.id}`}
                checked={scheduleEnabled}
                onCheckedChange={(enabled) => mode.mutate(enabled)}
                disabled={mode.isPending}
              />
            </Flex>
            <Stack gap="2">
              <Label htmlFor={`schedule-default-${board.id}`}>{ts("defaultPageLabel")}</Label>
              <Select
                value={defaultPageId || "__none__"}
                onValueChange={(value) => gapDefault.mutate(value === "__none__" ? null : value)}
                disabled={gapDefault.isPending}
              >
                <SelectTrigger id={`schedule-default-${board.id}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">{ts("noDefault")}</SelectItem>
                  {compatiblePages.map((page) => (
                    <SelectItem key={page.id} value={page.id}>
                      {page.name}
                    </SelectItem>
                  ))}
                  {collections.map((collection) => (
                    <SelectItem key={collection.id} value={collection.id}>
                      {collection.name} {ts("collectionSuffix")}
                    </SelectItem>
                  ))}
                  {unknownDefault && <SelectItem value={defaultPageId}>{defaultPageId}</SelectItem>}
                </SelectContent>
              </Select>
            </Stack>
          </>
        )}
        <Flex align="center" gap="3">
          <Switch
            id="schedule-defer-on-reenable"
            checked={deferOnReenable}
            onCheckedChange={(checked) => {
              setDeferOnReenable(checked);
              updateMutation.mutate(checked);
            }}
            disabled={updateMutation.isPending}
          />
          <Box>
            <label htmlFor="schedule-defer-on-reenable" className="text-sm font-medium cursor-pointer">
              {t("deferOnReenable")}
            </label>
            <Text size="xs" tone="muted" className="mt-0.5">
              {t("deferOnReenableHint")}
            </Text>
          </Box>
        </Flex>
      </Stack>
    </PageSection>
  );
}
