import {
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Flex,
  Label,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { EmptyState } from "@fiestaboard/ui/components/feedback/empty-state";
import { format } from "date-fns";
import { Calendar, ChevronRight, Edit, GalleryHorizontalEnd, Moon, Trash2 } from "lucide-react";
import { useMemo } from "react";

import { useTranslations } from "@/i18n/translations";
import type { Collection, Page, ScheduleEntry } from "@/lib/api";
import { isCollectionId } from "@/lib/api";
import type { ResolvedSilenceSchedule } from "@/lib/schedule-calendar";
import { sortSchedulesByStart } from "@/lib/schedule-sort";

interface ScheduleListViewProps {
  schedules: ScheduleEntry[];
  pages: Page[];
  collections?: Collection[];
  silenceSchedule?: ResolvedSilenceSchedule | null;
  onEdit: (schedule: ScheduleEntry) => void;
  onDelete: (id: string) => void;
  onToggleEnabled?: (schedule: ScheduleEntry, enabled: boolean) => void;
  onSilenceClick?: () => void;
}

const DAY_KEYS: Record<string, "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday"> = {
  monday: "monday",
  mon: "monday",
  tuesday: "tuesday",
  tue: "tuesday",
  wednesday: "wednesday",
  wed: "wednesday",
  thursday: "thursday",
  thu: "thursday",
  friday: "friday",
  fri: "friday",
  saturday: "saturday",
  sat: "saturday",
  sunday: "sunday",
  sun: "sunday",
};

function useFormatters() {
  const t = useTranslations("schedule");
  const tDays = useTranslations("daySelector.dayLabels");

  function formatDays(schedule: ScheduleEntry): string {
    if (schedule.recurrence_type === "annual_date" && schedule.annual_date) {
      const range = schedule.annual_end_date ? ` – ${schedule.annual_end_date}` : "";
      return `${schedule.annual_date}${range} (annual)`;
    }
    if (schedule.recurrence_type === "one_off_date" && schedule.one_off_date) {
      const range = schedule.one_off_end_date ? ` – ${schedule.one_off_end_date}` : "";
      return `${schedule.one_off_date}${range}`;
    }
    if (schedule.day_pattern === "all") return t("dayLabels.allDays");
    if (schedule.day_pattern === "weekdays") return t("dayLabels.monFri");
    if (schedule.day_pattern === "weekends") return t("dayLabels.satSun");
    if (schedule.day_pattern === "custom" && schedule.custom_days) {
      return schedule.custom_days
        .map((d) => {
          const trimmed = d.trim();
          const key = DAY_KEYS[trimmed.toLowerCase()];
          return key ? tDays(key) : trimmed;
        })
        .join(", ");
    }
    return "";
  }

  function formatTimeDisplay(schedule: ScheduleEntry): string {
    const startLabel =
      schedule.start_type === "sunrise"
        ? `☀↑${schedule.start_sun_offset ? ` ${schedule.start_sun_offset > 0 ? "+" : ""}${schedule.start_sun_offset}m` : ""}`
        : schedule.start_type === "sunset"
          ? `☀↓${schedule.start_sun_offset ? ` ${schedule.start_sun_offset > 0 ? "+" : ""}${schedule.start_sun_offset}m` : ""}`
          : schedule.start_time;

    const resolvedStart =
      schedule.resolved_start_time && schedule.start_type !== "fixed" ? ` (${schedule.resolved_start_time})` : "";

    if (!schedule.end_time && schedule.end_type === "fixed") {
      return `${startLabel}${resolvedStart} - ${t("openLabel")}`;
    }

    const endLabel =
      schedule.end_type === "sunrise"
        ? `☀↑${schedule.end_sun_offset ? ` ${schedule.end_sun_offset > 0 ? "+" : ""}${schedule.end_sun_offset}m` : ""}`
        : schedule.end_type === "sunset"
          ? `☀↓${schedule.end_sun_offset ? ` ${schedule.end_sun_offset > 0 ? "+" : ""}${schedule.end_sun_offset}m` : ""}`
          : schedule.end_time || t("openLabel");

    const resolvedEnd =
      schedule.resolved_end_time && schedule.end_type !== "fixed" ? ` (${schedule.resolved_end_time})` : "";

    return `${startLabel}${resolvedStart} - ${endLabel}${resolvedEnd}`;
  }

  return { formatDays, formatTimeDisplay };
}

export function ScheduleListView({
  schedules,
  pages,
  collections = [],
  silenceSchedule = null,
  onEdit,
  onDelete,
  onToggleEnabled,
  onSilenceClick,
}: ScheduleListViewProps) {
  const t = useTranslations("schedule");
  const tCommon = useTranslations("common");
  const { formatDays, formatTimeDisplay } = useFormatters();

  const showSilenceRow = !!silenceSchedule?.enabled;

  // Entries read chronologically, not in creation order.
  const sortedSchedules = useMemo(() => sortSchedulesByStart(schedules), [schedules]);

  const getPageName = (pageId: string): string => {
    if (isCollectionId(pageId)) {
      const collection = collections.find((c) => c.id === pageId);
      return collection?.name || pageId;
    }
    return pages.find((p) => p.id === pageId)?.name || pageId;
  };

  const renderSilenceRow = () => {
    if (!showSilenceRow || !silenceSchedule) return null;
    const [sH, sM] = silenceSchedule.startTimeLocal.split(":").map(Number);
    const [eH, eM] = silenceSchedule.endTimeLocal.split(":").map(Number);
    const startLabel = format(new Date(2000, 0, 1, sH, sM), "h:mm a");
    const endLabel = format(new Date(2000, 0, 1, eH, eM), "h:mm a");
    const timeRange = `${startLabel} – ${endLabel}`;
    const subtitle =
      silenceSchedule.mode === "indicator"
        ? t("silenceModeIndicatorSubtitle", { text: silenceSchedule.indicatorText || "SNOOZING" })
        : silenceSchedule.mode === "freeze"
          ? t("silenceModeFreezeSubtitle")
          : t("silenceModePageSubtitle", {
              name: pages.find((p) => p.id === silenceSchedule.pageId)?.name || silenceSchedule.pageId || "",
            });

    return (
      <button
        type="button"
        onClick={onSilenceClick}
        aria-label={t("silenceEventAriaLabel", { range: timeRange })}
        className="w-full text-left flex items-center justify-between p-4 border rounded-lg bg-muted/30 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors"
        data-testid="schedule-list-silence-row"
      >
        <Box className="flex-1 min-w-0">
          <Flex align="center" gap="2" className="mb-1">
            <Moon className="h-4 w-4 text-muted-foreground flex-shrink-0" aria-hidden="true" />
            <Text as="span" weight="medium">
              {t("silenceScheduleListTitle")}
            </Text>
          </Flex>
          <Text tone="muted" className="truncate">
            {timeRange} • {subtitle}
          </Text>
        </Box>
        <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0 ml-2" aria-hidden="true" />
      </button>
    );
  };

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="text-lg">{t("scheduleEntriesTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {schedules.length === 0 && !showSilenceRow ? (
          <EmptyState
            icon={Calendar}
            title={t("noSchedulesCreated")}
            description={t("useToolbarToAdd")}
            className="py-12"
          />
        ) : (
          <Stack gap="3">
            {renderSilenceRow()}
            {sortedSchedules.map((schedule) => {
              const pageName = getPageName(schedule.page_id);
              const toggleId = `schedule-enabled-${schedule.id}`;
              return (
                <Flex
                  key={schedule.id}
                  direction="col"
                  gap="3"
                  // Phone: description on top, controls on their own row beneath.
                  // Squeezing both into one row can't work — the text column's
                  // min-content plus the toggle and buttons is wider than a
                  // phone viewport, so the actions used to render off-screen
                  // (#1558). From `sm` up it's the original single row.
                  className="p-4 border rounded-lg sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                  data-testid="schedule-list-row"
                >
                  {/* min-w-0 lets the text column shrink past its min-content
                      width instead of pushing the actions out of the row. */}
                  <Box className="min-w-0 sm:flex-1">
                    <Flex align="center" gap="2" wrap className="mb-1">
                      {isCollectionId(schedule.page_id) && (
                        <GalleryHorizontalEnd className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      )}
                      <Text as="span" weight="medium" className="break-words">
                        {pageName}
                      </Text>
                      {!schedule.enabled && <Badge variant="secondary">{tCommon("disabled")}</Badge>}
                    </Flex>
                    <Text tone="muted" className="break-words">
                      {formatTimeDisplay(schedule)} • {formatDays(schedule)}
                    </Text>
                  </Box>
                  <Flex align="center" gap="2" className="sm:flex-shrink-0">
                    {onToggleEnabled && (
                      // The divider only reads as one on the single-row layout;
                      // stacked, the toggle and the buttons sit at opposite ends.
                      <Flex align="center" gap="2" className="sm:pr-2 sm:border-r sm:mr-1">
                        <Label htmlFor={toggleId} className="text-xs text-muted-foreground cursor-pointer">
                          {t("scheduleEntryForm.enabledLabel")}
                        </Label>
                        <Switch
                          id={toggleId}
                          checked={schedule.enabled}
                          onCheckedChange={(checked) => onToggleEnabled(schedule, checked)}
                          aria-label={t("toggleEnabledAriaLabel", { pageName })}
                        />
                      </Flex>
                    )}
                    {/* ml-auto pins Edit/Delete to the right edge of the stacked
                        control row; on the single-row layout they sit next to
                        the toggle exactly as before. */}
                    <Flex align="center" gap="2" className="ml-auto sm:ml-0">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onEdit(schedule)}
                        aria-label={t("editScheduleAriaLabel", { pageName })}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onDelete(schedule.id)}
                        aria-label={t("deleteScheduleAriaLabel", { pageName })}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </Flex>
                  </Flex>
                </Flex>
              );
            })}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
