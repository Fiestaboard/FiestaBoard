import {
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { useCurrentBoard } from "@/components/current-board-context";
import { useTranslations } from "@/i18n/translations";
import { api, type Collection, type Page } from "@/lib/api";
import { copyScheduleEntries, ScheduleCopyError } from "@/lib/schedule-copy";
export function ScheduleCopy({
  boardId,
  pages,
  collections,
}: {
  boardId?: string;
  pages: Page[];
  collections: Collection[];
}) {
  const { boards, currentBoard } = useCurrentBoard();
  const target = boards.find((board) => board.id === boardId) ?? (!boardId ? currentBoard : undefined);
  const sources = boards.filter((board) => board.id !== target?.id);
  const t = useTranslations("schedule.copy");
  const id = useId();
  const client = useQueryClient();
  const [source, setSource] = useState("");
  const entries = useQuery({
    queryKey: ["schedule-copy-source", source],
    queryFn: () => api.getSchedules(source),
    enabled: !!source,
  });
  const copy = useMutation({
    mutationFn: async () => {
      if (!target || !entries.data?.schedules.length) return;
      await copyScheduleEntries(entries.data.schedules, target, pages, collections);
    },
    onSettled: () => {
      client.invalidateQueries({ queryKey: ["schedules"] });
    },
  });
  if (!target || !sources.length) return null;
  return (
    <Collapsible>
      <CollapsibleTrigger asChild>
        <Button variant="outline">{t("open")}</Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <Stack gap="3" className="pt-4">
          <Text size="sm" tone="muted">
            {t("description")}
          </Text>
          <Label htmlFor={id}>{t("source")}</Label>
          <Select
            value={source}
            onValueChange={(value) => {
              setSource(value);
              copy.reset();
            }}
            disabled={copy.isPending}
          >
            <SelectTrigger id={id}>
              <SelectValue placeholder={t("source")} />
            </SelectTrigger>
            <SelectContent>
              {sources.map((board) => (
                <SelectItem key={board.id} value={board.id}>
                  {board.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            disabled={!entries.data?.schedules.length || entries.isFetching || copy.isPending || copy.isSuccess}
            onClick={() => copy.mutate()}
          >
            {t("run")}
          </Button>
          {entries.isError && (
            <Text role="alert" tone="destructive">
              {entries.error.message}
            </Text>
          )}
          {copy.isError && (
            <Text role="alert" tone="destructive">
              {copy.error instanceof ScheduleCopyError && copy.error.incompatible
                ? t("incompatible")
                : copy.error.message}
              {copy.error instanceof ScheduleCopyError && copy.error.remainingIds.length > 0
                ? ` ${t("partial", { ids: copy.error.remainingIds.join(", ") })}`
                : ""}
            </Text>
          )}
        </Stack>
      </CollapsibleContent>
    </Collapsible>
  );
}
