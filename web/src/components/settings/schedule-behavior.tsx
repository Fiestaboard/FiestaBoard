"use client";

import { Box, Flex, PageSection, Switch, Text } from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api, type BoardInstance, type BoardSettings } from "@/lib/api";

/** Schedule re-enabling behavior belongs to the explicitly targeted display. */
export function ScheduleBehavior({ board }: { board: BoardInstance }) {
  return <BoardScheduleBehavior key={board.id} board={board} />;
}

function BoardScheduleBehavior({ board }: { board: BoardInstance }) {
  const t = useTranslations("generalSettings");
  const queryClient = useQueryClient();
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
      icon={<CalendarClock />}
      title={t("scheduleBehaviorTitle")}
      description={t("scheduleBehaviorDescription")}
      {...anchorProps("settings.schedule_behavior")}
    >
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
    </PageSection>
  );
}
