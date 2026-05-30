"use client";

import { Calendar, Edit, GalleryHorizontalEnd, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Collection, Page, ScheduleEntry } from "@/lib/api";
import { isCollectionId } from "@/lib/api";

interface ScheduleListViewProps {
  schedules: ScheduleEntry[];
  pages: Page[];
  collections?: Collection[];
  onEdit: (schedule: ScheduleEntry) => void;
  onDelete: (id: string) => void;
  onToggleEnabled?: (schedule: ScheduleEntry, enabled: boolean) => void;
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
  onEdit,
  onDelete,
  onToggleEnabled,
}: ScheduleListViewProps) {
  const t = useTranslations("schedule");
  const tCommon = useTranslations("common");
  const { formatDays, formatTimeDisplay } = useFormatters();

  const getPageName = (pageId: string): string => {
    if (isCollectionId(pageId)) {
      const collection = collections.find((c) => c.id === pageId);
      return collection?.name || pageId;
    }
    return pages.find((p) => p.id === pageId)?.name || pageId;
  };

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="text-lg">{t("scheduleEntriesTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {schedules.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Calendar className="h-12 w-12 mx-auto mb-4" />
            <p>{t("noSchedulesCreated")}</p>
            <p className="text-sm mt-1">{t("useToolbarToAdd")}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {schedules.map((schedule) => {
              const pageName = getPageName(schedule.page_id);
              const toggleId = `schedule-enabled-${schedule.id}`;
              return (
                <div key={schedule.id} className="flex items-center justify-between p-4 border rounded-lg">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {isCollectionId(schedule.page_id) && (
                        <GalleryHorizontalEnd className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      )}
                      <span className="font-medium">{pageName}</span>
                      {!schedule.enabled && <Badge variant="secondary">{tCommon("disabled")}</Badge>}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {formatTimeDisplay(schedule)} • {formatDays(schedule)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {onToggleEnabled && (
                      <div className="flex items-center gap-2 pr-2 border-r mr-1">
                        <Label htmlFor={toggleId} className="text-xs text-muted-foreground cursor-pointer">
                          {t("scheduleEntryForm.enabledLabel")}
                        </Label>
                        <Switch
                          id={toggleId}
                          checked={schedule.enabled}
                          onCheckedChange={(checked) => onToggleEnabled(schedule, checked)}
                          aria-label={t("toggleEnabledAriaLabel", { pageName })}
                        />
                      </div>
                    )}
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
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
