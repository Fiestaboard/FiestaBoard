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
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
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

// Zoom presets: [label, px-per-hour, step-minutes, timeslots]
// step × timeslots = minutes per visual group.
// We keep step=15 at lower zoom levels (4 timeslots = 1 hour group) to limit
// DOM nodes. Only the highest levels drop to step=5 or step=1 where the grid
// is expanded enough to justify per-minute resolution.
const ZOOM_PRESETS: [string, number, number, number][] = [
  ["1×",  28,  15, 4],   // compact — 7 px / slot
  ["2×",  48,  15, 4],
  ["3×",  72,  15, 4],
  ["4×",  100, 15, 4],
  ["6×",  150, 5,  3],   // switch to 5-min grid
  ["8×",  240, 5,  3],
  ["12×", 360, 5,  3],
  ["16×", 480, 1,  1],   // minute-level
  ["24×", 720, 1,  1],
];
const DEFAULT_ZOOM = 0;
const MAX_ZOOM = ZOOM_PRESETS.length - 1;
const ZOOM_STORAGE_KEY = "schedule-calendar-zoom";

interface ScheduleCalendarViewProps {
  schedules: ScheduleEntry[];
  pages: Page[];
  carousels?: Carousel[];
  overlaps?: Overlap[];
  onEventClick: (schedule: ScheduleEntry) => void;
  onSlotSelect: (start: Date, end: Date) => void;
  onEventTimeChange: (scheduleId: string, startTime: string, endTime: string | null) => void;
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

  // Zoom state – persisted to localStorage
  const [zoomIndex, setZoomIndex] = useState<number>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem(ZOOM_STORAGE_KEY);
      const n = saved !== null ? parseInt(saved, 10) : NaN;
      if (!isNaN(n) && n >= 0 && n < ZOOM_PRESETS.length) return n;
    }
    return DEFAULT_ZOOM;
  });

  useEffect(() => {
    localStorage.setItem(ZOOM_STORAGE_KEY, String(zoomIndex));
  }, [zoomIndex]);

  const [, hourHeight, zoomStep, zoomTimeslots] = ZOOM_PRESETS[zoomIndex];
  const slotHeight = Math.round(hourHeight / zoomTimeslots);

  const handleZoomIn = useCallback(
    () => setZoomIndex((i) => Math.min(i + 1, MAX_ZOOM)),
    []
  );
  const handleZoomOut = useCallback(
    () => setZoomIndex((i) => Math.max(i - 1, 0)),
    []
  );
  const handleSliderChange = useCallback(
    (values: number[]) => setZoomIndex(values[0]),
    []
  );

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

  // Fetch sunrise/sunset times for today (used for slot markers)
  const [sunTimes, setSunTimes] = useState<{ sunrise: string | null; sunset: string | null } | null>(null);
  // Per-day sun times for the visible week (used for correct event positioning)
  const [sunTimesMap, setSunTimesMap] = useState<Record<string, { sunrise: string; sunset: string }> | undefined>(undefined);
  useEffect(() => {
    const weekStartStr = format(weekStart, "yyyy-MM-dd");
    api.getSunTimes().then((data) => {
      if (data.location_configured) {
        setSunTimes({ sunrise: data.sunrise, sunset: data.sunset });
      }
    }).catch(() => { /* ignore */ });
    api.getSunTimesWeek(weekStartStr).then((data) => {
      if (data.location_configured) {
        setSunTimesMap(data.dates);
      }
    }).catch(() => { /* ignore if location not configured or API unavailable */ });
  }, [weekStart]);

  // Transform schedules to calendar events
  const events = useMemo(
    () => schedulesToCalendarEvents(schedules, weekStart, pages, carousels, sunTimesMap),
    [schedules, weekStart, pages, carousels, sunTimesMap]
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
          onEventTimeChange(event.resource.scheduleId, startTime, orig.end_time ?? null);
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

  // Custom slot prop getter: hover styling + sun time markers
  const slotPropGetter = useCallback((slotDate: Date) => {
    const classes = ["schedule-slot"];
    if (sunTimes) {
      const slotH = slotDate.getHours();
      const slotM = slotDate.getMinutes();
      if (sunTimes.sunrise) {
        const [sunH, sunM] = sunTimes.sunrise.split(":").map(Number);
        if (slotH === sunH && Math.floor(slotM / zoomStep) * zoomStep === Math.floor(sunM / zoomStep) * zoomStep) {
          classes.push("sun-slot-sunrise");
        }
      }
      if (sunTimes.sunset) {
        const [sunH, sunM] = sunTimes.sunset.split(":").map(Number);
        if (slotH === sunH && Math.floor(slotM / zoomStep) * zoomStep === Math.floor(sunM / zoomStep) * zoomStep) {
          classes.push("sun-slot-sunset");
        }
      }
    }
    return { className: classes.join(" ") };
  }, [sunTimes, zoomStep]);

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

  // CSS variable overrides derived from current zoom level
  const calendarStyle = useMemo<React.CSSProperties>(() => ({
    "--rbc-hour-height": `${hourHeight}px`,
    "--rbc-slot-height": `${slotHeight}px`,
  } as React.CSSProperties), [hourHeight, slotHeight]);

  // Get visible days label for mobile
  const _visibleDaysLabel = useMemo(() => {
    const endDay = Math.min(mobileStartDay + 2, 6);
    return `${DAY_NAMES[mobileStartDay]} - ${DAY_NAMES[endDay]}`;
  }, [mobileStartDay]);

  return (
    <TooltipProvider>
    <div className="schedule-calendar-wrapper h-full flex flex-col">
      {/* Top bar: mobile day navigation (left) + zoom slider (right) */}
      <div className="flex items-center justify-between mb-2 px-1">
        {/* Mobile day navigation */}
        {isMobile ? (
          <div className="flex items-center gap-1">
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
        ) : (
          <div />
        )}

        {/* Zoom slider */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleZoomOut}
                disabled={zoomIndex === 0}
                className="h-7 w-7 p-0"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <Slider
                value={[zoomIndex]}
                min={0}
                max={MAX_ZOOM}
                step={1}
                onValueChange={handleSliderChange}
                className="w-24"
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={handleZoomIn}
                disabled={zoomIndex === MAX_ZOOM}
                className="h-7 w-7 p-0"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
              <span className="text-[10px] font-medium text-muted-foreground w-8 tabular-nums">
                {ZOOM_PRESETS[zoomIndex][0]}
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {zoomStep === 1 ? "1-minute grid" : `${zoomStep}-minute grid`}
          </TooltipContent>
        </Tooltip>
      </div>

      <div 
        ref={containerRef}
        className={`schedule-calendar-container flex-1 min-h-0 ${isMobile ? "schedule-calendar-mobile" : ""}`}
        data-start-day={mobileStartDay}
        style={calendarStyle}
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
          step={zoomStep}
          timeslots={zoomTimeslots}
          min={minTime}
          max={maxTime}
          eventPropGetter={eventPropGetter}
          slotPropGetter={slotPropGetter}
          components={components}
          toolbar={false}
          formats={{
            timeGutterFormat: (date: Date) =>
              zoomStep <= 5
                ? format(date, "h:mma").toLowerCase()
                : format(date, "ha").toLowerCase(),
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
    </TooltipProvider>
  );
}
