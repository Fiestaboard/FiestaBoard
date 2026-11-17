import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Code,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Input,
  Label,
  ListRow,
  ListRowGroup,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Slider,
  Stack,
  Text,
  Textarea,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { formatInTimeZone, fromZonedTime } from "date-fns-tz";
import { useId, useState } from "react";

import { BoardViewport } from "@/components/board-viewport";
import { useTranslations } from "@/i18n/translations";
import { api, type Collection, isCollectionId, type Page } from "@/lib/api";

/** H8 is deliberately a hub read: no client schedule or formula evaluation. */
export function ScheduleLookup({
  boardId,
  pages,
  collections,
  timezone = Intl.DateTimeFormat().resolvedOptions().timeZone,
}: {
  boardId?: string;
  pages: Page[];
  collections: Collection[];
  timezone?: string;
}) {
  const t = useTranslations("schedule.lookup");
  const id = useId();
  const [instant, setInstant] = useState(() => formatInTimeZone(new Date(), timezone, "yyyy-MM-dd'T'HH:mm"));
  const [checked, setChecked] = useState<{ at: string; boardId?: string } | null>(null);
  const [collectionId, setCollectionId] = useState("");
  const [valuesText, setValuesText] = useState("{}");
  const [validationError, setValidationError] = useState(false);
  const [dryRequest, setDryRequest] = useState<{
    at: string;
    boardId?: string;
    collectionId: string;
    values: Record<string, unknown>;
  } | null>(null);
  const current = checked?.boardId === boardId && checked !== null;
  const answer = useQuery({
    queryKey: ["schedule-lookup", boardId, checked?.at],
    queryFn: () => api.getActiveSchedule(boardId, checked!.at),
    enabled: current,
    retry: false,
  });
  const dryCurrent = current && dryRequest?.at === checked.at && dryRequest?.boardId === boardId;
  const dry = useQuery({
    queryKey: ["schedule-dry-run", dryRequest],
    queryFn: () =>
      api.dryRunCollection(dryRequest!.collectionId, {
        at: dryRequest!.at,
        values: dryRequest!.values,
        window_seconds: 86400,
        step_seconds: 900,
      }),
    enabled: dryCurrent,
    retry: false,
  });
  const name = (pageId: string | null | undefined) =>
    pages.find((page) => page.id === pageId)?.name ??
    collections.find((collection) => collection.id === pageId)?.name ??
    pageId ??
    t("none");
  const result = current ? answer.data : undefined;
  const dryResult = dryCurrent ? dry.data : undefined;
  const selectedCollection =
    collectionId || (isCollectionId(result?.page_id) ? result!.page_id! : (collections[0]?.id ?? ""));
  const selectedPageId = dryResult?.page_id ?? result?.resolved_page_id ?? result?.page_id;
  const page = pages.find((entry) => entry.id === selectedPageId);
  const pageDetail = useQuery({
    queryKey: ["schedule-preview-page", selectedPageId],
    queryFn: () => api.getPage(selectedPageId!),
    enabled: !!selectedPageId && !isCollectionId(selectedPageId) && !page?.template,
    retry: false,
  });
  const previewPage = page?.template ? page : pageDetail.data;
  const preview = useQuery({
    queryKey: [
      "schedule-preview-at",
      boardId,
      checked?.at,
      selectedPageId,
      dryCurrent ? dryRequest?.values : null,
      previewPage?.revision,
    ],
    queryFn: () =>
      api.previewSchedulePage(previewPage!, checked!.at, boardId, dryCurrent ? dryRequest?.values : undefined),
    enabled: current && !!selectedPageId && !!previewPage?.template,
    retry: false,
  });
  const clearAnswer = (value: string) => {
    setInstant(value);
    setChecked(null);
    setDryRequest(null);
  };
  const minute = instant ? Number(instant.slice(11, 13)) * 60 + Number(instant.slice(14, 16)) : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <Text size="sm" tone="muted">
          {t("description")}
        </Text>
      </CardHeader>
      <CardContent>
        <Stack gap="4">
          <Stack gap="2">
            <Label htmlFor={`${id}-instant`}>{t("instant")}</Label>
            <Input
              id={`${id}-instant`}
              type="datetime-local"
              value={instant}
              onChange={(event) => {
                clearAnswer(event.target.value);
              }}
            />
            <Button
              variant="outline"
              disabled={!instant || (current && answer.isFetching)}
              onClick={() => {
                setChecked({ at: fromZonedTime(instant, timezone).toISOString(), boardId });
                if (current) void answer.refetch();
                setDryRequest(null);
              }}
            >
              {t("check")}
            </Button>
          </Stack>
          <Text size="xs" tone="muted">
            {t("timeHint", { timezone })}
          </Text>
          <Slider
            aria-label={t("scrubber")}
            min={0}
            max={1439}
            step={15}
            value={[minute]}
            onValueChange={([value]) =>
              clearAnswer(
                `${instant.slice(0, 10)}T${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`,
              )
            }
            disabled={!instant}
          />
          {current && answer.isError && (
            <Text role="alert" tone="destructive">
              {answer.error.message}
            </Text>
          )}
          {result && (
            <Stack gap="3" role="region" aria-label={t("result")}>
              <ListRowGroup>
                <ListRow title={t("page")} meta={name(result.resolved_page_id ?? result.page_id)} />
                <ListRow title={t("source")} meta={t(`sources.${result.source}`)} />
                <ListRow title={t("reference")} meta={name(result.page_id)} />
              </ListRowGroup>
              {result.silenced && <Badge variant="outline">{t("silenced")}</Badge>}
              {result.temporary_override?.active && <Badge variant="outline">{t("override")}</Badge>}
              {preview.data && previewPage && (
                <BoardViewport
                  message={preview.data.lines.join("\n")}
                  deviceType={previewPage.device_type}
                  notesWide={previewPage.notes_wide}
                  notesTall={previewPage.notes_tall}
                  gridRows={previewPage.grid_rows ?? undefined}
                  gridCols={previewPage.grid_cols ?? undefined}
                  layout="phone-hero"
                  regionLabel={t("result")}
                />
              )}
              {preview.isError && (
                <Text role="alert" tone="destructive">
                  {preview.error.message}
                </Text>
              )}
              <Text size="xs" tone="muted">
                {t("futureLimit")}
              </Text>
            </Stack>
          )}
          {collections.length > 0 && (
            <Stack gap="3">
              <Label htmlFor={`${id}-collection`}>{t("collection")}</Label>
              <Select
                value={selectedCollection}
                onValueChange={(value) => {
                  setCollectionId(value);
                  setDryRequest(null);
                }}
              >
                <SelectTrigger id={`${id}-collection`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {collections.map((collection) => (
                    <SelectItem key={collection.id} value={collection.id}>
                      {collection.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Label htmlFor={`${id}-values`}>{t("values")}</Label>
              <Textarea
                id={`${id}-values`}
                value={valuesText}
                onChange={(event) => {
                  setValuesText(event.target.value);
                  setDryRequest(null);
                  setValidationError(false);
                }}
                aria-invalid={validationError}
              />
              {validationError && (
                <Text role="alert" tone="destructive">
                  {t("invalidValues")}
                </Text>
              )}
              <Button
                variant="outline"
                disabled={!current || !selectedCollection || (dryCurrent && dry.isFetching)}
                onClick={() => {
                  try {
                    const values: unknown = JSON.parse(valuesText);
                    if (!values || Array.isArray(values) || typeof values !== "object") throw new Error();
                    setValidationError(false);
                    setDryRequest({
                      at: checked!.at,
                      boardId,
                      collectionId: selectedCollection,
                      values: values as Record<string, unknown>,
                    });
                  } catch {
                    setValidationError(true);
                  }
                }}
              >
                {t("run")}
              </Button>
            </Stack>
          )}
          {dryCurrent && dry.isError && (
            <Text role="alert" tone="destructive">
              {dry.error.message}
            </Text>
          )}
          {dryResult && (
            <Stack gap="3" role="region" aria-label={t("collection")}>
              <Text weight="semibold">{name(dryResult.page_id)}</Text>
              {dryResult.rules?.length ? (
                <ListRowGroup>
                  {dryResult.rules.map((rule) => (
                    <ListRow
                      key={rule.index}
                      title={<Code>{rule.expression}</Code>}
                      description={rule.message ?? rule.error ?? rule.value}
                      meta={<Badge variant="outline">{rule.matched ? t("matched") : t("unmatched")}</Badge>}
                    />
                  ))}
                </ListRowGroup>
              ) : null}
              <Text size="sm" weight="semibold">
                {t("timeline")}
              </Text>
              <ListRowGroup>
                {dryResult.timeline.map((segment, index) => (
                  <ListRow
                    key={index}
                    title={name(segment.page_id)}
                    description={`${new Date(segment.from).toLocaleString()} – ${new Date(segment.until).toLocaleString()}`}
                  />
                ))}
              </ListRowGroup>
              {dryResult.truncated && (
                <Text role="status">{t("truncated", { reason: dryResult.truncated_reason ?? "" })}</Text>
              )}
              <Text size="sm">
                {t("shownOn")}: {dryResult.shown_on.join(", ") || t("none")}
              </Text>
              <Collapsible>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost">{t("raw")}</Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <Code className="block overflow-auto whitespace-pre-wrap break-all">
                    {JSON.stringify(dryResult, null, 2)}
                  </Code>
                </CollapsibleContent>
              </Collapsible>
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
