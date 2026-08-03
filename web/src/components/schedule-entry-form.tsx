"use client";

import {
  Alert,
  AlertDescription,
  Box,
  Button,
  Flex,
  Input,
  Label,
  List,
  ListItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { AlertCircle, AlertTriangle, GalleryHorizontalEnd, Loader2, Sunrise, Sunset, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { BoardSizeIndicator } from "@/components/board-size-indicator";
import { useCurrentBoard } from "@/components/current-board-context";
import { DaySelector } from "@/components/day-selector";
import { useTranslations } from "@/i18n/translations";
import type {
  Collection,
  DayPattern,
  RecurrenceType,
  ScheduleCreate,
  ScheduleEntry,
  ScheduleUpdate,
  TimeType,
} from "@/lib/api";
import { isCollectionId } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";

interface SchedulePageOption {
  id: string;
  name: string;
  /** Board geometry for size filtering; pages without it act as flagship. */
  device_type?: string;
  notes_wide?: number;
  notes_tall?: number;
}

interface ScheduleEntryFormProps {
  schedule?: ScheduleEntry;
  pages: SchedulePageOption[];
  collections?: Collection[];
  onSubmit: (data: ScheduleCreate | ScheduleUpdate) => Promise<void>;
  onCancel: () => void;
  onDelete?: () => void;
  prefillPageId?: string;
  prefillStartTime?: string;
  prefillEndTime?: string;
  prefillDayPattern?: DayPattern;
  prefillCustomDays?: string[];
}

// Generate 1-minute interval times for full scheduling flexibility
const generateTimeOptions = () => {
  const times: string[] = [];
  for (let hour = 0; hour < 24; hour++) {
    for (let minute = 0; minute < 60; minute++) {
      const h = hour.toString().padStart(2, "0");
      const m = minute.toString().padStart(2, "0");
      times.push(`${h}:${m}`);
    }
  }
  return times;
};

const TIME_OPTIONS = generateTimeOptions();

const TIME_TYPE_OPTIONS: TimeType[] = ["fixed", "sunrise", "sunset"];

const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));
const DAYS_IN_MONTH: Record<string, number> = {
  "01": 31,
  "02": 29,
  "03": 31,
  "04": 30,
  "05": 31,
  "06": 30,
  "07": 31,
  "08": 31,
  "09": 30,
  "10": 31,
  "11": 30,
  "12": 31,
};

const splitMMDD = (value: string | null | undefined): { month: string; day: string } => {
  if (!value) return { month: "", day: "" };
  const [m, d] = value.split("-");
  return { month: m || "", day: d || "" };
};

const joinMMDD = (month: string, day: string): string | null => (month && day ? `${month}-${day}` : null);

const todayISO = (): string => {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
};

export function ScheduleEntryForm({
  schedule,
  pages,
  collections = [],
  onSubmit,
  onCancel,
  onDelete,
  prefillPageId,
  prefillStartTime,
  prefillEndTime,
  prefillDayPattern,
  prefillCustomDays,
}: ScheduleEntryFormProps) {
  const t = useTranslations("schedule");
  const tc = useTranslations("common");
  const isEdit = Boolean(schedule);

  // Board the schedule targets: the app-wide current board (issue #1249).
  // Single-board installs see no change — every page for that board matches.
  const { currentBoard } = useCurrentBoard();

  // Use schedule values if editing, prefill values if creating from calendar, or defaults
  const [pageId, setPageId] = useState(schedule?.page_id || prefillPageId || "");
  const [startTime, setStartTime] = useState(schedule?.start_time || prefillStartTime || "09:00");
  const [endTime, setEndTime] = useState(schedule?.end_time || prefillEndTime || "17:00");
  const [hasEndTime, setHasEndTime] = useState(schedule ? schedule.end_time != null : true);
  const [dayPattern, setDayPattern] = useState<DayPattern>(schedule?.day_pattern || prefillDayPattern || "all");
  const [customDays, setCustomDays] = useState<string[]>(schedule?.custom_days || prefillCustomDays || []);
  const [enabled, setEnabled] = useState(schedule?.enabled !== false);

  // Sun schedule state
  const [startType, setStartType] = useState<TimeType>(schedule?.start_type || "fixed");
  const [startSunOffset, setStartSunOffset] = useState<number>(schedule?.start_sun_offset || 0);
  const [endType, setEndType] = useState<TimeType>(schedule?.end_type || "fixed");
  const [endSunOffset, setEndSunOffset] = useState<number>(schedule?.end_sun_offset || 0);

  // Recurrence state
  const [recurrenceType, setRecurrenceType] = useState<RecurrenceType>(schedule?.recurrence_type || "weekly");
  const initialAnnual = splitMMDD(schedule?.annual_date);
  const initialAnnualEnd = splitMMDD(schedule?.annual_end_date);
  const [annualMonth, setAnnualMonth] = useState<string>(initialAnnual.month);
  const [annualDay, setAnnualDay] = useState<string>(initialAnnual.day);
  const [annualEndMonth, setAnnualEndMonth] = useState<string>(initialAnnualEnd.month);
  const [annualEndDay, setAnnualEndDay] = useState<string>(initialAnnualEnd.day);
  const [annualHasRange, setAnnualHasRange] = useState<boolean>(Boolean(schedule?.annual_end_date));
  const [oneOffDate, setOneOffDate] = useState<string>(schedule?.one_off_date || "");
  const [oneOffEndDate, setOneOffEndDate] = useState<string>(schedule?.one_off_end_date || "");
  const [oneOffHasRange, setOneOffHasRange] = useState<boolean>(Boolean(schedule?.one_off_end_date));

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Only pages whose size matches the current board are offered (issue #1249).
  // The currently selected page is always kept so editing an existing entry
  // never renders an empty Select.
  const visiblePages = useMemo(() => {
    if (!currentBoard) return pages;
    return pages.filter((p) => p.id === pageId || pagesCompatibleWithBoard(p, currentBoard));
  }, [pages, currentBoard, pageId]);

  // Non-fatal size warning for the current selection: a collection with some
  // members that don't fit the board, or a plain page that doesn't fit
  // (possible when editing a pre-existing entry). Mirrors the backend
  // `warnings` from #1245.
  const sizeWarning = useMemo(() => {
    if (!currentBoard || !pageId) return null;
    if (isCollectionId(pageId)) {
      const collection = collections.find((c) => c.id === pageId);
      if (!collection) return null;
      const members = collection.page_ids
        .map((pid) => pages.find((p) => p.id === pid))
        .filter((p): p is SchedulePageOption => Boolean(p));
      if (members.length === 0) return null;
      const misfits = members.filter((p) => !pagesCompatibleWithBoard(p, currentBoard));
      if (misfits.length === 0) return null;
      return t("scheduleEntryForm.collectionSizeWarning", { count: misfits.length, total: members.length });
    }
    const page = pages.find((p) => p.id === pageId);
    if (page && !pagesCompatibleWithBoard(page, currentBoard)) {
      return t("scheduleEntryForm.incompatiblePageWarning");
    }
    return null;
  }, [currentBoard, pageId, collections, pages, t]);

  // Validation
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  useEffect(() => {
    const errors: string[] = [];

    if (!pageId) {
      errors.push(t("scheduleEntryForm.validationSelectPage"));
    }

    // Validate times are not identical (zero-duration schedule)
    // Note: endMinutes < startMinutes is valid (midnight rollover, e.g. 23:00-03:00)
    // Only check when both times are fixed and end time is set
    if (hasEndTime && startType === "fixed" && endType === "fixed") {
      const startMinutes = timeToMinutes(startTime);
      const endMinutes = timeToMinutes(endTime);
      if (startMinutes === endMinutes) {
        errors.push(t("scheduleEntryForm.validationEndTimeDifferent"));
      }
    }

    // Validate custom days (weekly only)
    if (recurrenceType === "weekly" && dayPattern === "custom" && customDays.length === 0) {
      errors.push(t("scheduleEntryForm.validationSelectDay"));
    }

    // Validate date-specific recurrences
    if (recurrenceType === "annual_date") {
      if (!annualMonth || !annualDay) {
        errors.push(t("scheduleEntryForm.validationAnnualDateRequired"));
      }
      if (annualHasRange && (!annualEndMonth || !annualEndDay)) {
        errors.push(t("scheduleEntryForm.validationAnnualDateRequired"));
      }
    } else if (recurrenceType === "one_off_date") {
      if (!oneOffDate) {
        errors.push(t("scheduleEntryForm.validationOneOffDateRequired"));
      }
      if (oneOffHasRange) {
        if (!oneOffEndDate) {
          errors.push(t("scheduleEntryForm.validationOneOffDateRequired"));
        } else if (oneOffDate && oneOffEndDate < oneOffDate) {
          errors.push(t("scheduleEntryForm.validationEndDateBeforeStart"));
        }
      }
    }

    setValidationErrors(errors);
  }, [
    pageId,
    startTime,
    endTime,
    hasEndTime,
    dayPattern,
    customDays,
    startType,
    endType,
    recurrenceType,
    annualMonth,
    annualDay,
    annualEndMonth,
    annualEndDay,
    annualHasRange,
    oneOffDate,
    oneOffEndDate,
    oneOffHasRange,
  ]);

  const timeToMinutes = (time: string): number => {
    const [h, m] = time.split(":").map(Number);
    return h * 60 + m;
  };

  const getTimeTypeLabel = (type: TimeType): string => {
    switch (type) {
      case "fixed":
        return t("scheduleEntryForm.timeTypeFixed");
      case "sunrise":
        return t("scheduleEntryForm.timeTypeSunrise");
      case "sunset":
        return t("scheduleEntryForm.timeTypeSunset");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (validationErrors.length > 0) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const baseData = {
        page_id: pageId,
        start_time: startTime,
        end_time: hasEndTime ? endTime : null,
        enabled,
        start_type: startType,
        start_sun_offset: startType !== "fixed" ? startSunOffset : 0,
        end_type: endType,
        end_sun_offset: endType !== "fixed" ? endSunOffset : 0,
      };

      let data: ScheduleCreate | ScheduleUpdate;
      if (recurrenceType === "weekly") {
        data = {
          ...baseData,
          recurrence_type: "weekly",
          day_pattern: dayPattern,
          custom_days: dayPattern === "custom" ? customDays : undefined,
          annual_date: null,
          annual_end_date: null,
          one_off_date: null,
          one_off_end_date: null,
        };
      } else if (recurrenceType === "annual_date") {
        data = {
          ...baseData,
          recurrence_type: "annual_date",
          day_pattern: "all",
          annual_date: joinMMDD(annualMonth, annualDay),
          annual_end_date: annualHasRange ? joinMMDD(annualEndMonth, annualEndDay) : null,
          one_off_date: null,
          one_off_end_date: null,
        };
      } else {
        data = {
          ...baseData,
          recurrence_type: "one_off_date",
          day_pattern: "all",
          one_off_date: oneOffDate || null,
          one_off_end_date: oneOffHasRange ? oneOffEndDate || null : null,
          annual_date: null,
          annual_end_date: null,
        };
      }

      await onSubmit(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("scheduleEntryForm.submitError"));
      setIsSubmitting(false);
    }
  };

  const handleDayChange = (pattern: DayPattern, days?: string[]) => {
    setDayPattern(pattern);
    if (days) {
      setCustomDays(days);
    }
  };

  return (
    <Box as="form" onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Page / Collection Selection */}
      <Stack gap="2">
        <Label htmlFor="page">{t("scheduleEntryForm.pageOrCollection")}</Label>
        <Select value={pageId} onValueChange={setPageId} modal={false}>
          <SelectTrigger id="page">
            <SelectValue placeholder={t("scheduleEntryForm.selectPageOrCollection")} />
          </SelectTrigger>
          <SelectContent>
            {collections.length > 0 && (
              <>
                <Box className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                  {t("scheduleEntryForm.collectionsGroup")}
                </Box>
                {collections.map((collection) => (
                  <SelectItem key={collection.id} value={collection.id}>
                    <Flex align="center" gap="2">
                      <GalleryHorizontalEnd className="h-3.5 w-3.5" />
                      {collection.name}
                    </Flex>
                  </SelectItem>
                ))}
                <Box className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                  {t("scheduleEntryForm.pagesGroup")}
                </Box>
              </>
            )}
            {visiblePages.map((page) => (
              <SelectItem key={page.id} value={page.id}>
                <Flex align="center" gap="2">
                  {page.name}
                  {page.device_type && (
                    <BoardSizeIndicator
                      deviceType={page.device_type}
                      notesWide={page.notes_wide}
                      notesTall={page.notes_tall}
                    />
                  )}
                </Flex>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {sizeWarning && (
          <Alert variant="default" className="border-warning/50 bg-warning/10">
            <AlertTriangle className="h-4 w-4 text-warning" />
            <AlertDescription className="text-sm">{sizeWarning}</AlertDescription>
          </Alert>
        )}
      </Stack>

      {/* Time Selection */}
      <Stack gap="4">
        {/* Start Time */}
        <Stack gap="2">
          <Label htmlFor="start-time">{t("scheduleEntryForm.startTime")}</Label>
          <Flex gap="2">
            <Select value={startType} onValueChange={(v) => setStartType(v as TimeType)}>
              <SelectTrigger className="w-[140px]" aria-label={t("scheduleEntryForm.startTimeType")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIME_TYPE_OPTIONS.map((type) => (
                  <SelectItem key={`start-type-${type}`} value={type}>
                    <Flex align="center" gap="1.5">
                      {type === "sunrise" && <Sunrise className="h-3.5 w-3.5" />}
                      {type === "sunset" && <Sunset className="h-3.5 w-3.5" />}
                      {getTimeTypeLabel(type)}
                    </Flex>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {startType === "fixed" ? (
              <Select value={startTime} onValueChange={setStartTime}>
                <SelectTrigger id="start-time" className="flex-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {TIME_OPTIONS.map((time) => (
                    <SelectItem key={`start-${time}`} value={time}>
                      {time}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Flex align="center" gap="2" className="flex-1">
                <Input
                  type="number"
                  value={startSunOffset}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    setStartSunOffset(isNaN(val) ? 0 : val);
                  }}
                  className="w-20"
                  aria-label={t("scheduleEntryForm.sunOffset")}
                />
                <Text as="span" size="xs" tone="muted" className="whitespace-nowrap">
                  {t("scheduleEntryForm.sunOffsetHint")}
                </Text>
              </Flex>
            )}
          </Flex>
          {startType !== "fixed" && schedule?.resolved_start_time && (
            <Text tone="muted" size="xs" className="flex items-center gap-1">
              {startType === "sunrise" ? <Sunrise className="h-3 w-3" /> : <Sunset className="h-3 w-3" />}
              {t("scheduleEntryForm.resolvedTime", { time: schedule.resolved_start_time })}
            </Text>
          )}
        </Stack>

        {/* End Time */}
        {hasEndTime && (
          <Stack gap="2">
            <Label htmlFor="end-time">{t("scheduleEntryForm.endTime")}</Label>
            <Flex gap="2">
              <Select value={endType} onValueChange={(v) => setEndType(v as TimeType)}>
                <SelectTrigger className="w-[140px]" aria-label={t("scheduleEntryForm.endTimeType")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIME_TYPE_OPTIONS.map((type) => (
                    <SelectItem key={`end-type-${type}`} value={type}>
                      <Flex align="center" gap="1.5">
                        {type === "sunrise" && <Sunrise className="h-3.5 w-3.5" />}
                        {type === "sunset" && <Sunset className="h-3.5 w-3.5" />}
                        {getTimeTypeLabel(type)}
                      </Flex>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {endType === "fixed" ? (
                <Select value={endTime} onValueChange={setEndTime}>
                  <SelectTrigger id="end-time" className="flex-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-60">
                    {TIME_OPTIONS.map((time) => (
                      <SelectItem key={`end-${time}`} value={time}>
                        {time}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Flex align="center" gap="2" className="flex-1">
                  <Input
                    type="number"
                    value={endSunOffset}
                    onChange={(e) => {
                      const val = parseInt(e.target.value);
                      setEndSunOffset(isNaN(val) ? 0 : val);
                    }}
                    className="w-20"
                    aria-label={t("scheduleEntryForm.sunOffset")}
                  />
                  <Text as="span" size="xs" tone="muted" className="whitespace-nowrap">
                    {t("scheduleEntryForm.sunOffsetHint")}
                  </Text>
                </Flex>
              )}
            </Flex>
            {endType !== "fixed" && schedule?.resolved_end_time && (
              <Text tone="muted" size="xs" className="flex items-center gap-1">
                {endType === "sunrise" ? <Sunrise className="h-3 w-3" /> : <Sunset className="h-3 w-3" />}
                {t("scheduleEntryForm.resolvedTime", { time: schedule.resolved_end_time })}
              </Text>
            )}
          </Stack>
        )}

        {/* End time toggle */}
        <Flex align="center" gap="2">
          <Switch id="has-end-time" checked={hasEndTime} onCheckedChange={setHasEndTime} />
          <Label htmlFor="has-end-time" className="text-sm text-muted-foreground">
            {t("scheduleEntryForm.setEndTime")}
          </Label>
          {!hasEndTime && (
            <Text as="span" size="xs" tone="muted">
              ({t("scheduleEntryForm.openEndedHint")})
            </Text>
          )}
        </Flex>
      </Stack>

      {/* Recurrence Selection */}
      <Stack gap="2">
        <Label htmlFor="recurrence">{t("scheduleEntryForm.recurrenceLabel")}</Label>
        <Select value={recurrenceType} onValueChange={(v) => setRecurrenceType(v as RecurrenceType)}>
          <SelectTrigger id="recurrence">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="weekly">{t("scheduleEntryForm.recurrenceWeekly")}</SelectItem>
            <SelectItem value="annual_date">{t("scheduleEntryForm.recurrenceAnnual")}</SelectItem>
            <SelectItem value="one_off_date">{t("scheduleEntryForm.recurrenceOneOff")}</SelectItem>
          </SelectContent>
        </Select>
        <Text size="xs" tone="muted">
          {recurrenceType === "weekly"
            ? t("scheduleEntryForm.recurrenceWeeklyDescription")
            : recurrenceType === "annual_date"
              ? t("scheduleEntryForm.recurrenceAnnualDescription")
              : t("scheduleEntryForm.recurrenceOneOffDescription")}
        </Text>
      </Stack>

      {recurrenceType === "weekly" && (
        <DaySelector value={dayPattern} customDays={customDays} onChange={handleDayChange} />
      )}

      {recurrenceType === "annual_date" && (
        <Stack gap="3" className="rounded-lg border p-4">
          <Stack gap="2">
            <Label>{t("scheduleEntryForm.annualDateLabel")}</Label>
            <Flex gap="2">
              <Select value={annualMonth} onValueChange={setAnnualMonth}>
                <SelectTrigger className="flex-1" aria-label="Month">
                  <SelectValue placeholder="MM" />
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {MONTH_OPTIONS.map((m) => (
                    <SelectItem key={`annual-m-${m}`} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={annualDay} onValueChange={setAnnualDay}>
                <SelectTrigger className="flex-1" aria-label="Day">
                  <SelectValue placeholder="DD" />
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {Array.from({ length: DAYS_IN_MONTH[annualMonth] || 31 }, (_, i) =>
                    String(i + 1).padStart(2, "0"),
                  ).map((d) => (
                    <SelectItem key={`annual-d-${d}`} value={d}>
                      {d}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Flex>
          </Stack>
          <Flex align="center" gap="2">
            <Switch id="annual-has-range" checked={annualHasRange} onCheckedChange={setAnnualHasRange} />
            <Label htmlFor="annual-has-range" className="text-sm text-muted-foreground">
              {t("scheduleEntryForm.useDateRange")}
            </Label>
          </Flex>
          {annualHasRange && (
            <Stack gap="2">
              <Label>{t("scheduleEntryForm.annualEndDateLabel")}</Label>
              <Flex gap="2">
                <Select value={annualEndMonth} onValueChange={setAnnualEndMonth}>
                  <SelectTrigger className="flex-1" aria-label="End month">
                    <SelectValue placeholder="MM" />
                  </SelectTrigger>
                  <SelectContent className="max-h-60">
                    {MONTH_OPTIONS.map((m) => (
                      <SelectItem key={`annual-em-${m}`} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={annualEndDay} onValueChange={setAnnualEndDay}>
                  <SelectTrigger className="flex-1" aria-label="End day">
                    <SelectValue placeholder="DD" />
                  </SelectTrigger>
                  <SelectContent className="max-h-60">
                    {Array.from({ length: DAYS_IN_MONTH[annualEndMonth] || 31 }, (_, i) =>
                      String(i + 1).padStart(2, "0"),
                    ).map((d) => (
                      <SelectItem key={`annual-ed-${d}`} value={d}>
                        {d}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Flex>
            </Stack>
          )}
          <Text size="xs" tone="muted">
            {t("scheduleEntryForm.dateOverrideHint")}
          </Text>
        </Stack>
      )}

      {recurrenceType === "one_off_date" && (
        <Stack gap="3" className="rounded-lg border p-4">
          <Stack gap="2">
            <Label htmlFor="one-off-date">{t("scheduleEntryForm.oneOffDateLabel")}</Label>
            <Input
              id="one-off-date"
              type="date"
              value={oneOffDate}
              min={todayISO()}
              onChange={(e) => setOneOffDate(e.target.value)}
            />
          </Stack>
          <Flex align="center" gap="2">
            <Switch id="one-off-has-range" checked={oneOffHasRange} onCheckedChange={setOneOffHasRange} />
            <Label htmlFor="one-off-has-range" className="text-sm text-muted-foreground">
              {t("scheduleEntryForm.useDateRange")}
            </Label>
          </Flex>
          {oneOffHasRange && (
            <Stack gap="2">
              <Label htmlFor="one-off-end-date">{t("scheduleEntryForm.oneOffEndDateLabel")}</Label>
              <Input
                id="one-off-end-date"
                type="date"
                value={oneOffEndDate}
                min={oneOffDate || undefined}
                onChange={(e) => setOneOffEndDate(e.target.value)}
              />
            </Stack>
          )}
          <Text size="xs" tone="muted">
            {t("scheduleEntryForm.dateOverrideHint")}
          </Text>
        </Stack>
      )}

      {/* Enabled Toggle */}
      <Flex align="center" justify="between" className="rounded-lg border p-4">
        <Stack gap="0.5">
          <Label htmlFor="enabled" className="text-base">
            Enabled
          </Label>
          <Text tone="muted">Schedule will be active when enabled</Text>
        </Stack>
        <Switch id="enabled" checked={enabled} onCheckedChange={setEnabled} />
      </Flex>

      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            <List marker="disc" gap="1" className="list-inside pl-0">
              {validationErrors.map((err, i) => (
                <ListItem key={i}>{err}</ListItem>
              ))}
            </List>
          </AlertDescription>
        </Alert>
      )}

      {/* Actions */}
      <Flex justify="between" gap="2">
        <Box>
          {isEdit && onDelete && (
            <Button type="button" variant="destructive" onClick={onDelete} disabled={isSubmitting}>
              <Trash2 className="mr-2 h-4 w-4" />
              {tc("delete")}
            </Button>
          )}
        </Box>
        <Flex gap="2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {tc("cancel")}
          </Button>
          <Button type="submit" disabled={validationErrors.length > 0 || isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEdit ? t("scheduleEntryForm.updateSchedule") : t("scheduleEntryForm.createSchedule")}
          </Button>
        </Flex>
      </Flex>
    </Box>
  );
}
