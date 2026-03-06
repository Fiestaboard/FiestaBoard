"use client";

import { useMemo, useCallback, useState, useEffect, useRef } from "react";
import { Calendar, dateFnsLocalizer, Views } from "react-big-calendar";
import withDragAndDrop, {
  type EventInteractionArgs,
} from "react-big-calendar/lib/addons/dragAndDrop";
import {
  format,
  parse,
  startOfWeek,
  getDay,
  addDays,
} from "date-fns";
import { enUS } from "date-fns/locale/en-US";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ScheduleEntry, Page, Overlap, Carousel } from "@/lib/api";
import {
  schedulesToCalendarEvents,
  extractTimeFromDate,
  type CalendarEvent,
} from "@/lib/schedule-calendar";
import { ScheduleEvent } from "./schedule-event";
import "react-big-calendar/lib/css/react-big-calendar.css";
import "react-big-calendar/lib/addons/dragAndDrop/styles.css";
import "@/styles/calendar.css";

// Setup the localizer with date-fns
const locales = {
  "en-US": enUS,
};

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: () => startOfWeek(new Date(), { weekStartsOn: 0 }),
  getDay,
  locales,
});

// Create DnD-enabled calendar
const DnDCalendar = withDragAndDrop<CalendarEvent>(Calendar);

// Day names for mobile navigation indicator
const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface ScheduleCalendarViewProps {
  schedules: ScheduleEntry[];
  pages: Page[];
  carousels?: Carousel[];
  overlaps?: Overlap[];
  onEventClick: (schedule: ScheduleEntry) => void;
  onSlotSelect: (start: Date, end: Date) => void;
  onEventTimeChange: (scheduleId: string, startTime: string, endTime: string) => void;
}

export function ScheduleCalendarView({
  schedules,
  pages,
  carousels = [],
  overlaps = [],
  onEventClick,
  onSlotSelect,
  onEventTimeChange,
}: ScheduleCalendarViewProps) {
  // Track mobile state
  const [isMobile, setIsMobile] = useState(false);
  const [mobileStartDay, setMobileStartDay] = useState(0); // 0 = Sunday
  const containerRef = useRef<HTMLDivElement>(null);

  // Check for mobile viewport
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Use current week as reference (doesn't matter which week since this is a template)
  const weekStart = useMemo(
    () => startOfWeek(new Date(), { weekStartsOn: 0 }),
    []
  );

  // Calculate the date to show based on mobile navigation
  const displayDate = useMemo(() => {
    if (!isMobile) return weekStart;
    return addDays(weekStart, mobileStartDay);
  }, [weekStart, isMobile, mobileStartDay]);

  // Transform schedules to calendar events
  const events = useMemo(
    () => schedulesToCalendarEvents(schedules, weekStart, pages, carousels),
    [schedules, weekStart, pages, carousels]
  );


  // Get IDs of schedules that have overlaps
  const overlappingScheduleIds = useMemo(() => {
    const ids = new Set<string>();
    for (const overlap of overlaps) {
      ids.add(overlap.schedule1_id);
      ids.add(overlap.schedule2_id);
    }
    return ids;
  }, [overlaps]);

  // Handle event click
  const handleSelectEvent = useCallback(
    (event: CalendarEvent) => {
      onEventClick(event.resource.originalSchedule);
    },
    [onEventClick]
  );

  // Handle slot selection (clicking empty time)
  const handleSelectSlot = useCallback(
    ({ start, end }: { start: Date; end: Date }) => {
      onSlotSelect(start, end);
    },
    [onSlotSelect]
  );

  // Handle event drag (move) or resize
  const handleEventDropOrResize = useCallback(
    ({ event, start, end }: EventInteractionArgs<CalendarEvent>) => {
      const startTime = extractTimeFromDate(start as Date);
      const endTime = extractTimeFromDate(end as Date);

      if (event.resource.isMidnightSplit) {
        const orig = event.resource.originalSchedule;
        if (event.resource.splitPart === "evening") {
          // Evening part: end is always pinned to the midnight boundary.
          // Only the start time can be changed; orig.end_time is always preserved.
          onEventTimeChange(event.resource.scheduleId, startTime, orig.end_time);
        } else {
          // Morning part: start must stay at midnight (00:00)
          if (startTime !== "00:00") {
            return; // Revert – can't change midnight boundary
          }
          onEventTimeChange(event.resource.scheduleId, orig.start_time, endTime);
        }
      } else {
        onEventTimeChange(event.resource.scheduleId, startTime, endTime);
      }
    },
    [onEventTimeChange]
  );

  // Mobile navigation handlers
  const handlePrevDays = useCallback(() => {
    setMobileStartDay((prev) => Math.max(0, prev - 3));
  }, []);

  const handleNextDays = useCallback(() => {
    setMobileStartDay((prev) => Math.min(4, prev + 3)); // Max 4 so we show days 4-6 (Thu-Sat)
  }, []);

  // Custom event prop getter for styling
  const eventPropGetter = useCallback(
    (event: CalendarEvent) => {
      const isOverlapping = overlappingScheduleIds.has(
        event.resource.scheduleId
      );
      const isDisabled = !event.resource.enabled;

      return {
        className: `schedule-event ${isOverlapping ? "schedule-event-conflict" : ""} ${isDisabled ? "schedule-event-disabled" : ""}`,
      };
    },
    [overlappingScheduleIds]
  );

  // Custom slot prop getter for hover styling
  const slotPropGetter = useCallback(() => {
    return {
      className: "schedule-slot",
    };
  }, []);

  // Custom components - just the event renderer, no toolbar needed for template
  const components = useMemo(
    () => ({
      event: ScheduleEvent,
      toolbar: () => null,
    }),
    []
  );

  // Full 24 hours
  const minTime = useMemo(() => {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    return date;
  }, []);

  const maxTime = useMemo(() => {
    const date = new Date();
    date.setHours(23, 59, 59, 999);
    return date;
  }, []);

  // Get visible days label for mobile
  const visibleDaysLabel = useMemo(() => {
    const endDay = Math.min(mobileStartDay + 2, 6);
    return `${DAY_NAMES[mobileStartDay]} - ${DAY_NAMES[endDay]}`;
  }, [mobileStartDay]);

  return (
    <div className="schedule-calendar-wrapper">
      {/* Mobile Navigation */}
      {isMobile && (
        <div className="flex items-center justify-between mb-2 px-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={handlePrevDays}
            disabled={mobileStartDay === 0}
            className="h-8 px-2"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="flex gap-1">
            {DAY_NAMES.map((day, idx) => (
              <button
                key={day}
                onClick={() => setMobileStartDay(Math.min(idx, 4))}
                className={`w-7 h-7 rounded-full text-xs font-medium transition-colors ${
                  idx >= mobileStartDay && idx < mobileStartDay + 3
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted"
                }`}
              >
                {day[0]}
              </button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleNextDays}
            disabled={mobileStartDay >= 4}
            className="h-8 px-2"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}

      <div 
        ref={containerRef}
        className={`schedule-calendar-container ${isMobile ? "schedule-calendar-mobile" : ""}`}
        data-start-day={mobileStartDay}
      >
        <DnDCalendar
          localizer={localizer}
          events={events}
          startAccessor="start"
          endAccessor="end"
          date={displayDate}
          view={Views.WEEK}
          views={[Views.WEEK]}
          defaultView={Views.WEEK}
          onSelectEvent={handleSelectEvent}
          onSelectSlot={handleSelectSlot}
          onEventDrop={handleEventDropOrResize}
          onEventResize={handleEventDropOrResize}
          selectable
          resizable
          step={15}
          timeslots={4}
        min={minTime}
        max={maxTime}
        eventPropGetter={eventPropGetter}
          slotPropGetter={slotPropGetter}
          components={components}
          toolbar={false}
          formats={{
            timeGutterFormat: (date: Date) => format(date, "ha").toLowerCase(),
            eventTimeRangeFormat: ({ start, end }: { start: Date; end: Date }) =>
              `${format(start, "h:mm a")} - ${format(end, "h:mm a")}`,
            dayHeaderFormat: (date: Date) => format(date, "EEE"),
          }}
          tooltipAccessor={(event: CalendarEvent) =>
            `${event.title}\n${format(event.start, "h:mm a")} - ${format(event.end, "h:mm a")}`
          }
          draggableAccessor={(event: CalendarEvent) => !event.resource.isMidnightSplit}
          resizableAccessor={() => true}
          longPressThreshold={150}
        />
      </div>
    </div>
  );
}
