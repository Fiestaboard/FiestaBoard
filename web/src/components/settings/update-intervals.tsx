"use client";

import { Flex, Input, Label, PageSection, Stack, Text } from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Timer } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api, type BoardInstance, type BoardSettings, type PollingSettings } from "@/lib/api";

import { isPluginOutputBoard, isVirtualBoard } from "./output-boards";

type IntervalFieldName = keyof PollingSettings;

/** A required target keeps these controls independent of the sidebar selection. */
export function UpdateIntervals({ board }: { board: BoardInstance }) {
  return <BoardUpdateIntervals key={board.id} board={board} />;
}

function BoardUpdateIntervals({ board }: { board: BoardInstance }) {
  const t = useTranslations("generalSettings");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();
  const serverValues: PollingSettings = {
    interval_seconds: board.polling_interval_seconds ?? 15,
    board_read_interval_local: board.board_read_interval_local ?? 30,
    board_read_interval_cloud: board.board_read_interval_cloud ?? 180,
  };
  const [saved, setSaved] = useState(serverValues);
  const [draft, setDraft] = useState(() => ({
    interval_seconds: String(serverValues.interval_seconds),
    board_read_interval_local: String(serverValues.board_read_interval_local),
    board_read_interval_cloud: String(serverValues.board_read_interval_cloud),
  }));
  if (
    useDepsChanged([board.polling_interval_seconds, board.board_read_interval_local, board.board_read_interval_cloud])
  ) {
    setSaved(serverValues);
    setDraft({
      interval_seconds: String(serverValues.interval_seconds),
      board_read_interval_local: String(serverValues.board_read_interval_local),
      board_read_interval_cloud: String(serverValues.board_read_interval_cloud),
    });
  }

  const mutation = useMutation({
    mutationFn: ({ field, value }: { field: IntervalFieldName; value: number }) =>
      api.updatePollingSettings({ [field]: value }, board.id),
    onSuccess: (result, { field, value }) => {
      const persisted = result[field] ?? value;
      setSaved((previous) => ({ ...previous, [field]: persisted }));
      setDraft((previous) => ({ ...previous, [field]: String(persisted) }));
      const boardField = field === "interval_seconds" ? "polling_interval_seconds" : field;
      queryClient.setQueryData<BoardSettings>(
        queryKeys.boardSettings,
        (previous) =>
          previous && {
            ...previous,
            boards: previous.boards.map((item) => (item.id === board.id ? { ...item, [boardField]: persisted } : item)),
          },
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      toast.success(t(field === "interval_seconds" ? "toastPollingUpdated" : "toastBoardReadIntervalUpdated"));
    },
    onError: (error: Error, { field }) => {
      setDraft((previous) => ({ ...previous, [field]: String(saved[field]) }));
      toast.error(
        t(field === "interval_seconds" ? "toastPollingFailed" : "toastBoardReadIntervalFailed", {
          error: error.message,
        }),
      );
    },
  });

  const fields = [
    {
      field: "interval_seconds",
      id: "polling-interval",
      min: 10,
      label: "boardUpdateIntervalLabel",
      description: "boardUpdateIntervalDescription",
    },
    {
      field: "board_read_interval_local",
      id: "board-read-local",
      min: 20,
      label: "boardReadIntervalLocalLabel",
      description: "boardReadIntervalLocalDescription",
    },
    {
      field: "board_read_interval_cloud",
      id: "board-read-cloud",
      min: 20,
      label: "boardReadIntervalCloudLabel",
      description: "boardReadIntervalCloudDescription",
    },
  ] as const;

  const readMode = board.output_config?.api_mode ?? board.api_mode;
  const visibleFields = fields.filter(({ field }) => {
    if (field === "interval_seconds") return true;
    if (isVirtualBoard(board)) return false;
    // An output plugin can read back through its own transport; its api_mode
    // compatibility field does not describe that capability.
    if (isPluginOutputBoard(board)) return true;
    if (readMode === "cloud") return field === "board_read_interval_cloud";
    if (readMode === "local") return field === "board_read_interval_local";
    return true;
  });

  return (
    <PageSection
      icon={<Timer />}
      title={t("updateIntervalsTitle")}
      description={t("updateIntervalsDescription")}
      contentClassName="space-y-6"
      {...anchorProps("settings.polling")}
    >
      {visibleFields.map(({ field, id, min, label, description }) => (
        <Stack key={field} gap="2">
          <Label htmlFor={id} className="text-sm font-medium">
            {t(label)}
          </Label>
          <Text size="xs" tone="muted">
            {t(description)}
          </Text>
          <Flex align="center" gap="3">
            <Input
              id={id}
              type="number"
              min={min}
              max={3600}
              step={1}
              required
              value={draft[field]}
              onChange={(event) => setDraft((previous) => ({ ...previous, [field]: event.target.value }))}
              onBlur={(event) => {
                if (!event.currentTarget.reportValidity()) return;
                const value = Number(draft[field]);
                if (value !== saved[field]) mutation.mutate({ field, value });
              }}
              disabled={mutation.isPending}
              className="w-32"
            />
            <Text as="span" tone="muted">
              {tc("seconds")}
            </Text>
          </Flex>
          {field === "board_read_interval_cloud" && Number(draft[field]) < 60 && (
            <Text size="xs" tone="warning">
              {t("boardReadIntervalWarning")}
            </Text>
          )}
        </Stack>
      ))}
    </PageSection>
  );
}
