import {
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Code,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Flex,
  Grid,
  Input,
  Label,
  ListRow,
  ListRowGroup,
  SegmentedControl,
  SegmentedControlItem,
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
import { formatInTimeZone, fromZonedTime, toZonedTime } from "date-fns-tz";
import { useId, useState } from "react";

import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type Collection, isCollectionId, type Page } from "@/lib/api";
import { scheduleTimezone } from "@/lib/schedule-timezone";

import { SchedulePagePreview } from "./schedule-page-preview";
import { ScheduleSampleValues } from "./schedule-sample-values";

/** H8 is deliberately a hub read: no client schedule or formula evaluation. */
export function ScheduleLookup(props: {
  boardId?: string;
  pages: Page[];
  collections: Collection[];
  timezone?: string;
}) {
  const resolved = scheduleTimezone(props.timezone);
  return (
    <ScheduleLookupBody
      key={`${props.boardId ?? "default"}:${resolved.zone}`}
      {...props}
      timezone={resolved.zone}
      timezoneFallback={resolved.fallback}
    />
  );
}
function ScheduleLookupBody({
  boardId,
  pages,
  collections,
  timezone,
  timezoneFallback,
}: {
  boardId?: string;
  pages: Page[];
  collections: Collection[];
  timezone: string;
  timezoneFallback: boolean;
}) {
  const t = useTranslations("schedule.lookup");
  const id = useId();
  const locale = useLocale();
  const [instant, setInstant] = useState(() => formatInTimeZone(new Date(), timezone, "yyyy-MM-dd'T'HH:mm"));
  const [checked, setChecked] = useState<{ at: string; boardId?: string } | null>(null);
  const [collectionId, setCollectionId] = useState("");
  const [quickMoment, setQuickMoment] = useState("now");
  const [missingText, setMissingText] = useState("");
  const [valuesText, setValuesText] = useState("{}");
  const [validationError, setValidationError] = useState(false);
  const [dryRequest, setDryRequest] = useState<{
    at: string;
    boardId?: string;
    collectionId: string;
    values: Record<string, unknown>;
    missing: string[];
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
        missing: dryRequest!.missing,
        window_seconds: 86400,
        step_seconds: 1800,
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
  const dryResult = dryCurrent && !dry.isError ? dry.data : undefined;
  const selectedCollection =
    collectionId || (isCollectionId(result?.page_id) ? result!.page_id! : (collections[0]?.id ?? ""));
  const actualPageId = result?.resolved_page_id !== undefined ? result.resolved_page_id : result?.page_id;
  const clearAnswer = (value: string) => {
    setQuickMoment("");
    setInstant(value);
    setChecked(null);
    setDryRequest(null);
  };
  const formatMoment = (value: string) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? t("none")
      : date.toLocaleString(locale, { timeZone: timezone, dateStyle: "medium", timeStyle: "short" });
  };
  const minute = instant ? Number(instant.slice(11, 13)) * 60 + Number(instant.slice(14, 16)) : 0;
  return (
    <Stack gap="4">
      <Card className="gap-4 py-5">
        <CardHeader className="px-4 sm:px-5">
          <CardTitle>{t("title")}</CardTitle>
          <Text size="sm" tone="muted">
            {t("description")}
          </Text>
        </CardHeader>
        <CardContent className="px-4 sm:px-5">
          <Stack gap="4">
            {timezoneFallback && (
              <Text role="status" size="sm" tone="muted">
                {t("timezoneFallback")}
              </Text>
            )}
            <Flex gap="3" align="end" justify="between" wrap>
              <SegmentedControl
                aria-label={t("quickMoments")}
                value={quickMoment}
                onValueChange={(moment) => {
                  const now = new Date();
                  const date = toZonedTime(now, timezone);
                  if (moment === "tonight") date.setHours(21, 0, 0, 0);
                  if (moment === "tomorrow") {
                    date.setDate(date.getDate() + 1);
                    date.setHours(15, 0, 0, 0);
                  }
                  if (moment === "saturday") {
                    date.setDate(date.getDate() + ((6 - date.getDay() + 7) % 7));
                    date.setHours(12, 30, 0, 0);
                  }
                  const wall =
                    moment === "now"
                      ? formatInTimeZone(now, timezone, "yyyy-MM-dd'T'HH:mm")
                      : `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}T${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
                  clearAnswer(wall);
                  setQuickMoment(moment);
                }}
                wrap
              >
                <SegmentedControlItem value="now">{t("quickNow")}</SegmentedControlItem>
                <SegmentedControlItem value="tonight">{t("quickTonight")}</SegmentedControlItem>
                <SegmentedControlItem value="tomorrow">{t("quickTomorrow")}</SegmentedControlItem>
                <SegmentedControlItem value="saturday">{t("quickSaturday")}</SegmentedControlItem>
              </SegmentedControl>
              <Flex gap="2" align="stretch" className="w-full min-w-0 flex-col sm:w-auto sm:flex-row sm:items-end">
                <Stack gap="2" className="min-w-0 flex-1">
                  <Label htmlFor={`${id}-instant`}>{t("instant")}</Label>
                  <Input
                    id={`${id}-instant`}
                    type="datetime-local"
                    value={instant}
                    onChange={(event) => {
                      clearAnswer(event.target.value);
                    }}
                  />
                </Stack>
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
              </Flex>
            </Flex>
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
            <Text size="xs" tone="muted">
              {t("timeHint", { timezone })}
            </Text>
            {current && answer.isError && (
              <Text role="alert" tone="destructive">
                {answer.error.message}
              </Text>
            )}
          </Stack>
        </CardContent>
      </Card>
      <Grid cols="1" lg={result && collections.length > 0 ? "2" : "1"} gap="4" className="items-start">
        {result && (
          <Card className="min-w-0 gap-4 py-5" role="region" aria-label={t("result")}>
            <CardHeader className="px-4 sm:px-5">
              <CardTitle>{t("result")}</CardTitle>
            </CardHeader>
            <CardContent className="px-4 sm:px-5">
              <Stack gap="3">
                <ListRowGroup>
                  <ListRow title={t("page")} meta={name(actualPageId)} />
                  <ListRow title={t("source")} meta={t(`sources.${result.source}`)} />
                  <ListRow title={t("reference")} meta={name(result.page_id)} />
                </ListRowGroup>
                {result.silenced && <Badge variant="outline">{t("silenced")}</Badge>}
                {result.temporary_override?.active && <Badge variant="outline">{t("override")}</Badge>}
                <SchedulePagePreview
                  pageId={actualPageId}
                  pages={pages}
                  at={checked!.at}
                  boardId={boardId}
                  label={t("actualPreview")}
                />
                <Text size="xs" tone="muted">
                  {t("futureLimit")}
                </Text>
              </Stack>
            </CardContent>
          </Card>
        )}
        {collections.length > 0 && (
          <Card className="min-w-0 gap-4 py-5">
            <CardHeader className="px-4 sm:px-5">
              <CardTitle>{t("collection")}</CardTitle>
            </CardHeader>
            <CardContent className="px-4 sm:px-5">
              <Stack gap="3">
                <Label htmlFor={`${id}-collection`} className="sr-only">
                  {t("collection")}
                </Label>
                <Flex gap="2" align="stretch" className="flex-col sm:flex-row sm:items-center">
                  <Box className="min-w-0 flex-1">
                    <Select
                      value={selectedCollection}
                      onValueChange={(value) => {
                        setCollectionId(value);
                        setDryRequest(null);
                      }}
                    >
                      <SelectTrigger id={`${id}-collection`} className="w-full min-w-0">
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
                  </Box>
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
                          missing: missingText
                            .split(/\r?\n/)
                            .map((path) => path.trim())
                            .filter(Boolean),
                        });
                      } catch {
                        setValidationError(true);
                      }
                    }}
                  >
                    {t("run")}
                  </Button>
                </Flex>
                <ScheduleSampleValues
                  value={valuesText}
                  onChange={(value) => {
                    setValuesText(value);
                    setDryRequest(null);
                    setValidationError(false);
                  }}
                />
                <Collapsible>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-auto min-h-8 whitespace-normal text-left">
                      {t("missing")}
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <Stack gap="2">
                      <Label htmlFor={`${id}-missing`}>{t("missing")}</Label>
                      <Textarea
                        id={`${id}-missing`}
                        value={missingText}
                        onChange={(event) => {
                          setMissingText(event.target.value);
                          setDryRequest(null);
                        }}
                      />
                    </Stack>
                  </CollapsibleContent>
                </Collapsible>
                {validationError && (
                  <Text role="alert" tone="destructive">
                    {t("invalidValues")}
                  </Text>
                )}

                {dryCurrent && dry.isError && (
                  <Text role="alert" tone="destructive">
                    {dry.error.message}
                  </Text>
                )}
                {dryResult && (
                  <Stack gap="3" role="region" aria-label={t("collection")}>
                    <Text weight="semibold">{name(dryResult.page_id)}</Text>
                    <Text size="sm" tone="muted">
                      {name(dryRequest!.collectionId)}
                    </Text>
                    <SchedulePagePreview
                      pageId={dryResult.page_id}
                      pages={pages}
                      at={dryRequest!.at}
                      boardId={boardId}
                      values={dryRequest!.values}
                      missing={dryRequest!.missing}
                      label={t("simulatedPreview")}
                    />
                    {dryResult.rules?.length ? (
                      <ListRowGroup>
                        {dryResult.rules.map((rule) => (
                          <ListRow
                            key={rule.index}
                            title={<Code>{rule.expression}</Code>}
                            description={rule.message ?? rule.error ?? rule.value}
                            meta={
                              <Badge variant="outline">
                                {dryResult.matched_rule === rule.index
                                  ? t("winningRule")
                                  : rule.matched
                                    ? t("matched")
                                    : t("unmatched")}
                              </Badge>
                            }
                          />
                        ))}
                      </ListRowGroup>
                    ) : null}
                    <Text size="sm" weight="semibold">
                      {t("sourceFreshness")}
                    </Text>
                    <ListRowGroup>
                      {Object.entries(dryResult.sources).map(([source, metadata]) => {
                        const info =
                          metadata && typeof metadata === "object" ? (metadata as Record<string, unknown>) : {};
                        const state = info.state;
                        return (
                          <ListRow
                            key={source}
                            title={source}
                            meta={
                              typeof state === "string" && ["fresh", "stale", "live", "none"].includes(state)
                                ? t(`sourceState.${state}`)
                                : t("sourceState.unknown")
                            }
                            description={
                              typeof info.updated_at === "string" ? formatMoment(info.updated_at) : t("none")
                            }
                          />
                        );
                      })}
                    </ListRowGroup>
                    <Text size="sm" weight="semibold">
                      {t("timeline")}
                    </Text>
                    <Flex aria-hidden="true" className="h-11 w-full gap-1 overflow-hidden">
                      {dryResult.timeline.map((segment, index) => (
                        <Box
                          key={index}
                          className={
                            index % 2 === 0
                              ? "min-w-0 overflow-hidden rounded bg-muted px-2 py-1"
                              : "min-w-0 overflow-hidden rounded bg-accent px-2 py-1"
                          }
                          style={{
                            flexBasis: 0,
                            flexGrow: Math.max(1, new Date(segment.until).getTime() - new Date(segment.from).getTime()),
                          }}
                          title={`${name(segment.page_id)} · ${formatMoment(segment.from)} – ${formatMoment(segment.until)}`}
                        >
                          <Text size="xs" className="truncate">
                            {name(segment.page_id)}
                          </Text>
                        </Box>
                      ))}
                    </Flex>
                    <ListRowGroup>
                      {dryResult.timeline.map((segment, index) => (
                        <ListRow
                          key={index}
                          title={name(segment.page_id)}
                          description={`${new Date(segment.from).toLocaleString(locale, { timeZone: timezone, dateStyle: "medium", timeStyle: "short" })} – ${new Date(segment.until).toLocaleString(locale, { timeZone: timezone, dateStyle: "medium", timeStyle: "short" })}`}
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
        )}
      </Grid>
    </Stack>
  );
}
