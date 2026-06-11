import { format } from "date-fns";
import { Moon } from "lucide-react";
import { useMemo } from "react";
import type { EventProps } from "react-big-calendar";

import { Badge } from "@/components/ui/badge";
import { useTranslations } from "@/i18n/translations";
import {
  type CalendarEvent,
  formatDayPattern,
  getPageColor,
  getPageColorLight,
  type ScheduleCalendarEvent,
  type SilenceCalendarEvent,
} from "@/lib/schedule-calendar";

interface ScheduleEventProps extends EventProps<CalendarEvent> {
  event: CalendarEvent;
}

function isSilenceEvent(event: CalendarEvent): event is SilenceCalendarEvent {
  return event.resource.kind === "silence";
}

export function ScheduleEvent({ event }: ScheduleEventProps) {
  if (isSilenceEvent(event)) {
    return <SilenceEvent event={event} />;
  }
  return <RegularScheduleEvent event={event} />;
}

function RegularScheduleEvent({ event }: { event: ScheduleCalendarEvent }) {
  const { resource } = event;

  // Generate consistent color based on schedule ID (so each schedule entry has unique color)
  const scheduleColor = useMemo(() => getPageColor(resource.scheduleId), [resource.scheduleId]);

  const scheduleColorLight = useMemo(() => getPageColorLight(resource.scheduleId), [resource.scheduleId]);

  // Day pattern display
  const dayPatternDisplay = useMemo(() => formatDayPattern(resource.originalSchedule), [resource.originalSchedule]);

  // Format time range with segment-specific labels for split events
  const { timeRange, continuationHint } = useMemo(() => {
    if (resource.isMidnightSplit) {
      const orig = resource.originalSchedule;
      const [startH, startM] = orig.start_time.split(":").map(Number);
      const endTimeStr = orig.end_time || "23:59";
      const [endH, endM] = endTimeStr.split(":").map(Number);
      const startDate = new Date(2000, 0, 1, startH, startM);
      const endDate = new Date(2000, 0, 1, endH, endM);
      const fullStart = format(startDate, "h:mma").toLowerCase();
      const fullEnd = format(endDate, "h:mma").toLowerCase();

      if (resource.splitPart === "evening") {
        return {
          timeRange: `${fullStart} - 12:00am`,
          continuationHint: `→ ${fullEnd}`,
        };
      }
      return {
        timeRange: `12:00am - ${fullEnd}`,
        continuationHint: `${fullStart} →`,
      };
    }
    const startTime = format(event.start, "h:mma").toLowerCase();
    const endTime = format(event.end, "h:mma").toLowerCase();
    return { timeRange: `${startTime} - ${endTime}`, continuationHint: null };
  }, [event.start, event.end, resource.isMidnightSplit, resource.originalSchedule, resource.splitPart]);

  const isMorningSplit = resource.isMidnightSplit && resource.splitPart === "morning";
  const isEveningSplit = resource.isMidnightSplit && resource.splitPart === "evening";
  const activeColor = resource.enabled ? scheduleColor : "var(--muted-foreground)";

  return (
    <div
      className="schedule-event-content h-full w-full overflow-hidden rounded px-1.5 py-1"
      data-testid={`calendar-event-${resource.scheduleId}`}
      data-schedule-id={resource.scheduleId}
      data-enabled={resource.enabled ? "true" : "false"}
      data-split={resource.isMidnightSplit ? resource.splitPart : "none"}
      style={{
        backgroundColor: resource.enabled ? scheduleColorLight : "var(--muted)",
        borderLeft: `2px solid ${resource.enabled ? scheduleColor : "color-mix(in oklch, var(--muted-foreground) 50%, transparent)"}`,
        opacity: resource.enabled ? 1 : 0.5,
        ...(isMorningSplit ? { borderTop: `1px dashed ${activeColor}` } : {}),
        ...(isEveningSplit ? { borderBottom: `1px dashed ${activeColor}` } : {}),
      }}
    >
      <div className="flex flex-col gap-0">
        {isMorningSplit && continuationHint && (
          <span className="text-[8px] leading-tight truncate opacity-85" style={{ color: activeColor }}>
            {continuationHint}
          </span>
        )}
        <div className="font-medium text-[10px] leading-tight truncate" style={{ color: activeColor }}>
          {event.title}
        </div>
        <span className="text-[9px] font-medium truncate" style={{ color: activeColor }}>
          {timeRange}
        </span>
        {isEveningSplit && continuationHint && (
          <span className="text-[8px] leading-tight truncate opacity-85" style={{ color: activeColor }}>
            {continuationHint}
          </span>
        )}
        {!resource.enabled && (
          <Badge variant="secondary" className="w-fit text-[10px] px-1 py-0 h-3.5">
            Off
          </Badge>
        )}
        {resource.dayPattern !== "all" && (
          <span className="text-[10px] text-muted-foreground truncate">{dayPatternDisplay}</span>
        )}
      </div>
    </div>
  );
}

function SilenceEvent({ event }: { event: SilenceCalendarEvent }) {
  const t = useTranslations("schedule");
  const { resource } = event;

  const { timeRange, continuationHint } = useMemo(() => {
    const [sH, sM] = resource.startTimeLocal.split(":").map(Number);
    const [eH, eM] = resource.endTimeLocal.split(":").map(Number);
    const fullStart = format(new Date(2000, 0, 1, sH, sM), "h:mma").toLowerCase();
    const fullEnd = format(new Date(2000, 0, 1, eH, eM), "h:mma").toLowerCase();
    if (resource.isMidnightSplit) {
      if (resource.splitPart === "evening") {
        return { timeRange: `${fullStart} - 12:00am`, continuationHint: `→ ${fullEnd}` };
      }
      return { timeRange: `12:00am - ${fullEnd}`, continuationHint: `${fullStart} →` };
    }
    return { timeRange: `${fullStart} - ${fullEnd}`, continuationHint: null };
  }, [resource.startTimeLocal, resource.endTimeLocal, resource.isMidnightSplit, resource.splitPart]);

  const subtitle = useMemo(() => {
    if (resource.mode === "indicator") {
      return t("silenceModeIndicatorSubtitle", { text: resource.indicatorText || "SNOOZING" });
    }
    if (resource.mode === "freeze") {
      return t("silenceModeFreezeSubtitle");
    }
    return t("silenceModePageSubtitle", { name: resource.pageName || "" });
  }, [t, resource.mode, resource.indicatorText, resource.pageName]);

  const isMorningSplit = resource.isMidnightSplit && resource.splitPart === "morning";
  const isEveningSplit = resource.isMidnightSplit && resource.splitPart === "evening";

  return (
    <div
      className="schedule-event-content h-full w-full overflow-hidden rounded px-1.5 py-1"
      data-testid="calendar-event-silence"
      data-split={resource.isMidnightSplit ? resource.splitPart : "none"}
      role="button"
      tabIndex={0}
      aria-label={t("silenceEventAriaLabel", { range: timeRange })}
    >
      <div className="flex flex-col gap-0">
        {isMorningSplit && continuationHint && (
          <span className="text-[8px] leading-tight truncate opacity-85">{continuationHint}</span>
        )}
        <div className="flex items-center gap-1">
          <Moon className="h-2.5 w-2.5 flex-shrink-0" aria-hidden="true" />
          <span className="font-medium text-[10px] leading-tight truncate">{t("silenceEventTitle")}</span>
        </div>
        <span className="text-[9px] font-medium truncate">{timeRange}</span>
        {isEveningSplit && continuationHint && (
          <span className="text-[8px] leading-tight truncate opacity-85">{continuationHint}</span>
        )}
        <span className="text-[9px] truncate opacity-80">{subtitle}</span>
      </div>
    </div>
  );
}
