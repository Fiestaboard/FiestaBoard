"use client";

import { useMemo } from "react";
import { format } from "date-fns";
import type { EventProps } from "react-big-calendar";
import { Badge } from "@/components/ui/badge";
import {
  type CalendarEvent,
  getPageColor,
  getPageColorLight,
  formatDayPattern,
} from "@/lib/schedule-calendar";

interface ScheduleEventProps extends EventProps<CalendarEvent> {
  event: CalendarEvent;
}

export function ScheduleEvent({ event }: ScheduleEventProps) {
  const { resource } = event;
  
  // Generate consistent color based on schedule ID (so each schedule entry has unique color)
  const scheduleColor = useMemo(
    () => getPageColor(resource.scheduleId),
    [resource.scheduleId]
  );
  
  const scheduleColorLight = useMemo(
    () => getPageColorLight(resource.scheduleId),
    [resource.scheduleId]
  );

  // Day pattern display
  const dayPatternDisplay = useMemo(
    () => formatDayPattern(resource.originalSchedule),
    [resource.originalSchedule]
  );

  // Format time range (e.g., "9:00a - 5:00p")
  // For midnight-split events, show the original schedule time range
  const timeRange = useMemo(() => {
    if (resource.isMidnightSplit) {
      const orig = resource.originalSchedule;
      const [startH, startM] = orig.start_time.split(":").map(Number);
      const [endH, endM] = orig.end_time.split(":").map(Number);
      // Arbitrary date; only hours/minutes matter for formatting
      const startDate = new Date(2000, 0, 1, startH, startM);
      const endDate = new Date(2000, 0, 1, endH, endM);
      return `${format(startDate, "h:mma").toLowerCase()} - ${format(endDate, "h:mma").toLowerCase()}`;
    }
    const startTime = format(event.start, "h:mma").toLowerCase();
    const endTime = format(event.end, "h:mma").toLowerCase();
    return `${startTime} - ${endTime}`;
  }, [event.start, event.end, resource.isMidnightSplit, resource.originalSchedule]);

  return (
    <div
      className="schedule-event-content h-full w-full overflow-hidden rounded px-1.5 py-1"
      style={{
        backgroundColor: resource.enabled ? scheduleColorLight : "hsl(var(--muted))",
        borderLeft: `2px solid ${resource.enabled ? scheduleColor : "hsl(var(--muted-foreground) / 0.5)"}`,
        opacity: resource.enabled ? 1 : 0.5,
      }}
    >
      <div className="flex flex-col gap-0">
        <div
          className="font-medium text-[10px] leading-tight truncate"
          style={{ color: resource.enabled ? scheduleColor : "hsl(var(--muted-foreground))" }}
        >
          {event.title}
        </div>
        <span 
          className="text-[9px] font-medium truncate opacity-80"
          style={{ color: resource.enabled ? scheduleColor : "hsl(var(--muted-foreground))" }}
        >
          {timeRange}
        </span>
        {!resource.enabled && (
          <Badge
            variant="secondary"
            className="w-fit text-[8px] px-1 py-0 h-3 opacity-70"
          >
            Off
          </Badge>
        )}
        {resource.dayPattern !== "all" && (
          <span className="text-[8px] text-muted-foreground/70 truncate">
            {dayPatternDisplay}
          </span>
        )}
      </div>
    </div>
  );
}
