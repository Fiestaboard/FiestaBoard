import {
  Alert,
  AlertDescription,
  Button,
  DEFAULT_SCHEDULE_ENTRY,
  type ScheduleDay,
  ScheduleEntryForm as KitScheduleEntryForm,
  type ScheduleEntryFormLabels,
  type ScheduleEntryValue,
  Stack,
} from "@fiestaboard/ui";
import {
  type ComponentPropsWithoutRef,
  forwardRef,
  type ReactNode,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { useCurrentBoard } from "@/components/current-board-context";
import type { ScheduleFormHandle } from "@/components/schedule-editor-bridge-context";
import type { ScheduleEntryForm as LegacyScheduleEntryForm } from "@/components/schedule-entry-form";
import { useLocale, useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { isCollectionId } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";

type Props = ComponentPropsWithoutRef<typeof LegacyScheduleEntryForm> & {
  /** Host notice about the current, unsaved value (BB-C-1: the overlap callout), shown above the fields. */
  notice?: (value: ScheduleEntryValue) => ReactNode;
  /** BB-C-5: "compact" is the 07d phone sheet (the kit tucks the rarer fields behind More options). */
  layout?: "default" | "compact";
};
const DAYS: ScheduleDay[] = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
function canonicalDays(values: string[] | null | undefined): ScheduleDay[] | null {
  return values
    ? values
        .map((value) => DAYS.find((day) => day.slice(0, 3) === value.toLowerCase().slice(0, 3)))
        .filter((day): day is ScheduleDay => !!day)
    : null;
}
/** The host owns filtering, revisions and the AI bridge; the kit owns editing/validation/presentation. */
export const ScheduleEntryAdapter = forwardRef<ScheduleFormHandle, Props>(function ScheduleEntryAdapter(
  {
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
    notice,
    layout = "default",
  },
  ref,
) {
  const t = useTranslations("schedule.scheduleEntryForm");
  const ta = useTranslations("schedule.adapter");
  const td = useTranslations("daySelector");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { currentBoard } = useCurrentBoard();
  const [revision] = useState(() =>
    schedule?.edit_protocol === "schedule-revision-v1" ? schedule.revision : undefined,
  );
  const [value, setValue] = useState<ScheduleEntryValue>(() => ({
    ...DEFAULT_SCHEDULE_ENTRY,
    page_id: schedule?.page_id ?? prefillPageId ?? "",
    start_time: schedule?.start_time ?? prefillStartTime ?? "09:00",
    end_time: schedule ? (schedule.end_time ?? null) : (prefillEndTime ?? "17:00"),
    day_pattern: schedule?.day_pattern ?? prefillDayPattern ?? "all",
    custom_days: canonicalDays(schedule?.custom_days ?? prefillCustomDays),
    enabled: schedule?.enabled ?? true,
    start_type: schedule?.start_type ?? "fixed",
    end_type: schedule?.end_type ?? "fixed",
    start_sun_offset: schedule?.start_sun_offset ?? 0,
    end_sun_offset: schedule?.end_sun_offset ?? 0,
    recurrence_type: schedule?.recurrence_type ?? "weekly",
    annual_date: schedule?.annual_date ?? null,
    annual_end_date: schedule?.annual_end_date ?? null,
    one_off_date: schedule?.one_off_date ?? null,
    one_off_end_date: schedule?.one_off_end_date ?? null,
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useImperativeHandle(
    ref,
    () => ({
      setField: (field, next) => {
        if (field === "custom_days" && Array.isArray(next))
          setValue((previous) => ({ ...previous, custom_days: canonicalDays(next.map(String)) }));
        else if (field === "enabled") setValue((previous) => ({ ...previous, enabled: Boolean(next) }));
        else if (field === "end_time" && next === null) setValue((previous) => ({ ...previous, end_time: null }));
        else if ((field === "start_sun_offset" || field === "end_sun_offset") && typeof next === "number")
          setValue((previous) => ({ ...previous, [field]: next }));
        else if (field !== "custom_days" && typeof next === "string")
          setValue((previous) => ({ ...previous, [field]: next }));
      },
    }),
    [],
  );
  const visible = pages.filter(
    (page) => page.id === value.page_id || !currentBoard || pagesCompatibleWithBoard(page, currentBoard),
  );
  const misfits =
    currentBoard && isCollectionId(value.page_id)
      ? (collections.find((collection) => collection.id === value.page_id)?.page_ids ?? [])
          .map((id) => pages.find((page) => page.id === id))
          .filter((page) => page && !pagesCompatibleWithBoard(page, currentBoard))
      : [];
  const selected = pages.find((page) => page.id === value.page_id);
  const warning = misfits.length
    ? t("collectionSizeWarning", {
        count: misfits.length,
        total: collections.find((collection) => collection.id === value.page_id)?.page_ids.length ?? 0,
      })
    : currentBoard && selected && !pagesCompatibleWithBoard(selected, currentBoard)
      ? t("incompatiblePageWarning")
      : null;
  const labels: ScheduleEntryFormLabels = {
    target: t("pageOrCollection"),
    targetPlaceholder: t("selectPageOrCollection"),
    pages: t("pagesGroup"),
    collections: t("collectionsGroup"),
    onDisplay: (display) => `${ta("display")}: ${display}`,
    starts: t("startTimeType"),
    ends: t("endTimeType"),
    atATime: t("timeTypeFixed"),
    sunrise: t("timeTypeSunrise"),
    sunset: t("timeTypeSunset"),
    openEnded: ta("openEnded"),
    openEndedHint: t("openEndedHint"),
    startTime: t("startTime"),
    endTime: t("endTime"),
    startFallbackTime: ta("startFallback"),
    endFallbackTime: ta("endFallback"),
    fallbackHint: ta("fallbackHint"),
    offset: () => t("sunOffset"),
    sunOffset: (minutes, type) =>
      `${t(type === "sunrise" ? "timeTypeSunrise" : "timeTypeSunset")} ${minutes >= 0 ? "+" : ""}${minutes}`,
    resolvedTime: (time) => t("resolvedTime", { time }),
    repeat: t("recurrenceLabel"),
    weekly: t("recurrenceWeekly"),
    everyYear: t("recurrenceAnnual"),
    once: t("recurrenceOneOff"),
    days: td("daysLegend"),
    all: ta("allShort"),
    weekdays: ta("weekdaysShort"),
    weekends: ta("weekendsShort"),
    custom: ta("customShort"),
    customDays: td("selectCustomDaysAriaLabel"),
    dayShort: Object.fromEntries(DAYS.map((day) => [day, td(`dayLabels.${day}`)])) as Record<ScheduleDay, string>,
    month: t("monthAriaLabel"),
    day: t("dayAriaLabel"),
    lastMonth: t("endMonthAriaLabel"),
    lastDay: t("endDayAriaLabel"),
    months: Array.from({ length: 12 }, (_, month) =>
      new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2000, month, 1))),
    ),
    date: t("oneOffDateLabel"),
    severalDays: t("useDateRange"),
    enabled: t("enabledLabel"),
    enabledHint: t("enabledDescription"),
    save: tc("save"),
    saving: tc("saving"),
    delete: ta("delete"),
    moreOptions: ta("moreOptions"),
    timeRangeTo: ta("timeRangeTo"),
    startsAtSun: (type) => ta(`startsAtSun.${type}`),
    endsAtSun: (type) => ta(`endsAtSun.${type}`),
    entryOff: ta("entryOff"),
    errors: {
      page_id: t("validationSelectPage"),
      start_time: ta("invalidTime"),
      end_time: ta("invalidTime"),
      same: t("validationEndTimeDifferent"),
      custom_days: t("validationSelectDay"),
      date: t("validationOneOffDateRequired"),
      dateFormat: t("validationAnnualDateRequired"),
      before: t("validationEndDateBeforeStart"),
    },
  };
  const formRef = useRef<HTMLFormElement>(null);
  // Spotlight metadata is app wiring. The kit owns field markup and IDs.
  useLayoutEffect(() => {
    const form = formRef.current;
    if (!form) return;
    const attach = () => {
      for (const required of form.querySelectorAll<HTMLElement>("[data-slot=field-required] + .sr-only"))
        if (required.textContent !== ta("required")) required.textContent = ta("required");
      const allLabels = Array.from(form.querySelectorAll<HTMLElement>("label,span[id]"));
      const control = (label: string, index = 0) => {
        const found = allLabels.filter((item) => item.textContent?.startsWith(label))[index];
        return found?.getAttribute("for")
          ? document.getElementById(found.getAttribute("for")!)
          : found?.id
            ? Array.from(form.querySelectorAll<HTMLElement>("[aria-labelledby]")).find((item) =>
                item.getAttribute("aria-labelledby")?.split(" ").includes(found.id),
              )
            : undefined;
      };
      const anchors: [string, Element | null | undefined][] = [
        ["page", control(t("pageOrCollection"))],
        ["start-type", control(t("startTimeType"))],
        ["end-type", control(t("endTimeType"))],
        ["recurrence", control(t("recurrenceLabel"))],
        ["day-pattern", control(td("daysLegend"))],
        ["enabled", control(t("enabledLabel"))],
        ["start-time", control(t("startTime")) ?? control(ta("startFallback"))],
        ["end-time", control(t("endTime")) ?? control(ta("endFallback"))],
        ["start-sun-offset", value.start_type !== "fixed" ? control(t("sunOffset")) : undefined],
        [
          "end-sun-offset",
          value.end_type !== "fixed" ? control(t("sunOffset"), value.start_type !== "fixed" ? 1 : 0) : undefined,
        ],
      ];
      for (const [field, element] of anchors) element?.setAttribute("data-ai-anchor", `schedule.form.${field}`);
    };
    attach();
    const observer = new MutationObserver(attach);
    observer.observe(form, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [value, t, td, ta]);
  return (
    <Stack gap="4">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {warning && (
        <Alert>
          <AlertDescription>{warning}</AlertDescription>
        </Alert>
      )}
      {notice?.(value)}
      <KitScheduleEntryForm
        ref={formRef}
        value={value}
        onValueChange={setValue}
        targets={[
          ...visible.map((page) => ({ value: page.id, label: page.name, kind: "page" as const })),
          ...collections.map((collection) => ({
            value: collection.id,
            label: collection.name,
            kind: "collection" as const,
          })),
        ]}
        display={currentBoard?.name}
        resolvedStartTime={schedule?.resolved_start_time}
        resolvedEndTime={schedule?.resolved_end_time ?? undefined}
        onDelete={onDelete}
        busy={busy}
        layout={layout}
        labels={labels}
        {...anchorProps("schedule.entry-form")}
        onSubmit={async (normalized) => {
          setBusy(true);
          setError(null);
          try {
            await onSubmit({
              ...normalized,
              custom_days: normalized.custom_days ?? undefined,
              ...(revision ? { expected_revision: revision } : {}),
            });
          } catch (failure) {
            setError(failure instanceof Error ? failure.message : t("submitError"));
          } finally {
            setBusy(false);
          }
        }}
      />
      <Button variant="ghost" onClick={onCancel} disabled={busy}>
        {tc("cancel")}
      </Button>
    </Stack>
  );
});
