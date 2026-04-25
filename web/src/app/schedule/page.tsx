"use client";

import { useState, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import { ScheduleListView } from "./components";
import { queryKeys, useBoardSettings } from "@/hooks/use-board";

// Lazy load ScheduleCalendarView since it includes react-big-calendar (~150KB+)
const ScheduleCalendarView = dynamic(
  () => import("./components").then(mod => ({ default: mod.ScheduleCalendarView })),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-4">
        <Skeleton className="h-96 w-full" />
      </div>
    ),
  }
);
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, AlertCircle, AlertTriangle, List, CalendarDays, Calendar as CalendarIcon, Power, MapPin } from "lucide-react";
import Link from "next/link";
import { api, type ScheduleEntry, type ScheduleCreate, type ScheduleUpdate, type DayPattern, isCarouselId } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { PageToolbar } from "@/components/page-toolbar";
import { extractTimeFromDate, getDayNameFromDate } from "@/lib/schedule-calendar";
import { queryKeys as boardQueryKeys, useCarousels } from "@/hooks/use-board";

type ViewMode = "list" | "calendar";

const SCHEDULE_VIEW_MODE_KEY = "schedule-view-mode";
const NO_DEFAULT_PAGE = "__none__";

export default function SchedulePage() {
  const queryClient = useQueryClient();
  
  // Initialize viewMode from localStorage if available
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem(SCHEDULE_VIEW_MODE_KEY);
      if (saved === "list" || saved === "calendar") {
        return saved;
      }
    }
    return "list";
  });
  
  // Persist viewMode to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem(SCHEDULE_VIEW_MODE_KEY, viewMode);
  }, [viewMode]);
  const [showForm, setShowForm] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<ScheduleEntry | null>(null);
  const [deleteScheduleId, setDeleteScheduleId] = useState<string | null>(null);
  const { data: boardSettings } = useBoardSettings();
  const boards = boardSettings?.boards ?? [];
  const [selectedBoardId, setSelectedBoardId] = useState<string | "">("");
  const effectiveBoardId = boards.length > 1 ? selectedBoardId || boards[0]?.id || "" : undefined;

  useEffect(() => {
    if (boards.length > 1 && !selectedBoardId && boards[0]?.id) {
      setSelectedBoardId(boards[0].id);
    }
  }, [boards, selectedBoardId]);

  // Pre-fill data when creating from calendar slot selection
  const [prefillData, setPrefillData] = useState<{
    startTime?: string;
    endTime?: string;
    dayPattern?: DayPattern;
    customDays?: string[];
  } | null>(null);

  // Fetch schedules (scoped by board when multi-board)
  const { data: schedulesData, isLoading } = useQuery({
    queryKey: ["schedules", effectiveBoardId ?? "default"],
    queryFn: () => api.getSchedules(effectiveBoardId || undefined),
  });

  // Fetch pages for form
  const { data: pagesData } = useQuery({
    queryKey: ["pages"],
    queryFn: api.getPages,
  });

  // Fetch carousels for form
  const { data: carouselsData } = useCarousels();

  // Fetch location settings (needed for sunrise/sunset schedule resolution)
  const { data: locationData } = useQuery({
    queryKey: ["location-settings"],
    queryFn: api.getLocationSettings,
  });

  // Fetch validation (scoped by board)
  const { data: validation } = useQuery({
    queryKey: ["schedules", "validation", effectiveBoardId ?? "default"],
    queryFn: () => api.validateSchedules(effectiveBoardId || undefined),
    enabled: (schedulesData?.schedules.length || 0) > 0,
  });

  // Toggle schedule (per board when multi-board)
  const toggleSchedule = useMutation({
    mutationFn: (enabled: boolean) => api.setScheduleEnabled(enabled, effectiveBoardId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
      toast.success(schedulesData?.enabled ? "Schedule disabled" : "Schedule enabled");
    },
    onError: () => {
      toast.error("Failed to toggle schedule");
    },
  });

  // Create schedule (include board_id when multi-board)
  const createSchedule = useMutation({
    mutationFn: (data: ScheduleCreate) =>
      api.createSchedule({ ...data, ...(effectiveBoardId && { board_id: effectiveBoardId }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
      toast.success("Schedule created");
      setShowForm(false);
      setPrefillData(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to create schedule");
      throw error;
    },
  });

  // Update schedule
  const updateSchedule = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ScheduleUpdate }) =>
      api.updateSchedule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
      toast.success("Schedule updated");
      setShowForm(false);
      setEditingSchedule(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to update schedule");
      throw error;
    },
  });

  // Delete schedule
  const deleteSchedule = useMutation({
    mutationFn: (id: string) => api.deleteSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
      toast.success("Schedule deleted");
      setDeleteScheduleId(null);
    },
    onError: () => {
      toast.error("Failed to delete schedule");
    },
  });

  // Set default page (per board when multi-board)
  const setDefaultPage = useMutation({
    mutationFn: (pageId: string | null) => api.setDefaultPage(pageId, effectiveBoardId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
      toast.success("Default page updated");
    },
    onError: () => {
      toast.error("Failed to set default page");
    },
  });

  const handleSubmit = async (data: ScheduleCreate | ScheduleUpdate) => {
    if (editingSchedule) {
      await updateSchedule.mutateAsync({ id: editingSchedule.id, data });
    } else {
      await createSchedule.mutateAsync(data as ScheduleCreate);
    }
  };

  const handleEdit = useCallback((schedule: ScheduleEntry) => {
    setEditingSchedule(schedule);
    setPrefillData(null);
    setShowForm(true);
  }, []);

  const handleDelete = useCallback((id: string) => {
    setDeleteScheduleId(id);
  }, []);

  const handleAdd = useCallback(() => {
    setEditingSchedule(null);
    setPrefillData(null);
    setShowForm(true);
  }, []);

  const handleCloseForm = () => {
    setShowForm(false);
    setEditingSchedule(null);
    setPrefillData(null);
  };

  // Handle calendar slot selection (clicking on empty time)
  const handleSlotSelect = useCallback((start: Date, end: Date) => {
    const startTime = extractTimeFromDate(start);
    const endTime = extractTimeFromDate(end);
    const dayName = getDayNameFromDate(start);
    
    setPrefillData({
      startTime,
      endTime,
      dayPattern: "custom",
      customDays: [dayName],
    });
    setEditingSchedule(null);
    setShowForm(true);
  }, []);

  // Handle calendar event click
  const handleEventClick = useCallback((schedule: ScheduleEntry) => {
    handleEdit(schedule);
  }, [handleEdit]);

  // Handle calendar event time change (drag/resize)
  const handleEventTimeChange = useCallback(
    (scheduleId: string, startTime: string, endTime: string | null) => {
      updateSchedule.mutate({
        id: scheduleId,
        data: { start_time: startTime, end_time: endTime },
      });
    },
    [updateSchedule]
  );

  const getPageName = (pageId: string): string => {
    if (isCarouselId(pageId)) {
      const carousel = carouselsData?.carousels?.find((c) => c.id === pageId);
      return carousel ? `${carousel.name} (carousel)` : pageId;
    }
    return pagesData?.pages.find((p) => p.id === pageId)?.name || pageId;
  };

  const formatDaysCompact = (days: string[]): string => {
    if (!days || days.length === 0) return "";
    
    const weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday"];
    const weekends = ["saturday", "sunday"];
    const allDays = [...weekdays, ...weekends];
    
    const hasAllWeekdays = weekdays.every(d => days.includes(d));
    const hasAllWeekends = weekends.every(d => days.includes(d));
    const hasAllDays = allDays.every(d => days.includes(d));
    
    if (hasAllDays) return "Every day";
    if (hasAllWeekdays && days.length === 5) return "Weekdays";
    if (hasAllWeekends && days.length === 2) return "Weekends";
    
    return days
      .map(d => d.slice(0, 3).charAt(0).toUpperCase() + d.slice(1, 3))
      .join(", ");
  };

  if (isLoading) {
    return (
      <PageLayout>
        <Skeleton className="h-10 w-48 mb-4" />
        <Skeleton className="h-64 w-full" />
      </PageLayout>
    );
  }

  const schedules = schedulesData?.schedules || [];
  const pages = pagesData?.pages || [];
  const defaultPageId = schedulesData?.default_page_id;
  const locationConfigured = locationData?.latitude != null && locationData?.longitude != null;
  const hasSunSchedules = schedules.some(
    (s) => s.start_type !== "fixed" || s.end_type !== "fixed"
  );
  const scheduleEnabled = schedulesData?.enabled || false;
  const hasOverlaps = (validation?.overlaps?.length || 0) > 0;
  const hasGaps = (validation?.gaps?.length || 0) > 0;

  const isCalendarMode = viewMode === "calendar";
  const issueCount = hasOverlaps
    ? (validation?.overlaps?.length ?? 0)
    : (validation?.gaps?.length ?? 0);

  return (
    <PageLayout fillHeight={isCalendarMode}>
      {/* ── Page header ── */}
      <PageHeader
        icon={CalendarIcon}
        title="Schedule"
        className="flex-shrink-0"
        description={`Automate page rotation by time and day · ${Intl.DateTimeFormat().resolvedOptions().timeZone}`}
      />

      {/* ── Compact toolbar: everything in one row ── */}
      <TooltipProvider>
        <PageToolbar
          className="flex-shrink-0"
          left={
            /* View toggle */
            <div className="flex items-center gap-1 bg-muted p-1 rounded-md">
              <Button
                variant={viewMode === "list" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setViewMode("list")}
                className="px-3"
              >
                <List className="h-4 w-4 mr-1.5" />
                List
              </Button>
              <Button
                variant={viewMode === "calendar" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setViewMode("calendar")}
                className="px-3"
              >
                <CalendarDays className="h-4 w-4 mr-1.5" />
                Calendar
              </Button>
            </div>
          }
          right={
            <div className="flex items-center gap-2 flex-wrap justify-end">
              {/* Board selector (multi-board only) */}
              {boards.length > 1 && (
                <Select value={selectedBoardId} onValueChange={setSelectedBoardId}>
                  <SelectTrigger data-testid="board-selector" className="h-8 w-[130px] text-xs">
                    <SelectValue placeholder="Board" />
                  </SelectTrigger>
                  <SelectContent>
                    {boards.map((b: { id: string; name?: string }) => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.name || `Board ${b.id.slice(0, 8)}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              {/* Schedule on/off toggle */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <div data-testid="schedule-enabled-toggle" className="flex items-center gap-1.5 border rounded-md px-2.5 h-8 cursor-pointer" onClick={() => !toggleSchedule.isPending && toggleSchedule.mutate(!scheduleEnabled)}>
                    <Power className={`h-3.5 w-3.5 ${scheduleEnabled ? "text-green-500" : "text-muted-foreground"}`} />
                    <span className="text-xs font-medium">{scheduleEnabled ? "On" : "Off"}</span>
                    <Switch
                      checked={scheduleEnabled}
                      onCheckedChange={toggleSchedule.mutate}
                      disabled={toggleSchedule.isPending}
                      className="scale-75 pointer-events-none"
                      tabIndex={-1}
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {scheduleEnabled ? "Disable schedule mode" : "Enable schedule mode"}
                </TooltipContent>
              </Tooltip>

              {/* Default page for gaps */}
              <Select
                value={defaultPageId || NO_DEFAULT_PAGE}
                onValueChange={(value) => setDefaultPage.mutate(value === NO_DEFAULT_PAGE ? null : value)}
              >
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SelectTrigger data-testid="gap-default-select" className="h-8 w-[150px] text-xs">
                      <SelectValue placeholder="Gap default…" />
                    </SelectTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">Default page shown during schedule gaps</TooltipContent>
                </Tooltip>
                <SelectContent>
                  <SelectItem value={NO_DEFAULT_PAGE}>No default</SelectItem>
                  {pagesData?.pages.map((page) => (
                    <SelectItem key={page.id} value={page.id}>{page.name}</SelectItem>
                  ))}
                  {carouselsData?.carousels?.map((carousel) => (
                    <SelectItem key={carousel.id} value={carousel.id}>{carousel.name} (carousel)</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Validation indicator — floating icon that opens a detail dropdown */}
              {(hasOverlaps || hasGaps) && (
                <DropdownMenu>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className={`relative h-8 w-8 p-0 ${hasOverlaps ? "text-destructive hover:text-destructive" : "text-yellow-500 hover:text-yellow-500"}`}
                        >
                          {hasOverlaps
                            ? <AlertCircle className="h-4 w-4" />
                            : <AlertTriangle className="h-4 w-4" />}
                          <span className={`absolute -top-1 -right-1 h-4 min-w-4 px-0.5 text-[9px] font-bold rounded-full flex items-center justify-center text-white ${hasOverlaps ? "bg-destructive" : "bg-yellow-500"}`}>
                            {issueCount}
                          </span>
                        </Button>
                      </DropdownMenuTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">
                      {hasOverlaps ? `${issueCount} schedule conflict${issueCount !== 1 ? "s" : ""}` : `${issueCount} schedule gap${issueCount !== 1 ? "s" : ""}`}
                    </TooltipContent>
                  </Tooltip>
                  <DropdownMenuContent align="end" className="w-80">
                    <DropdownMenuLabel className={hasOverlaps ? "text-destructive" : "text-yellow-600 dark:text-yellow-400"}>
                      {hasOverlaps ? "Schedule Conflicts" : "Schedule Gaps"}
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {hasOverlaps
                      ? validation?.overlaps?.map((overlap, i) => (
                          <DropdownMenuItem key={i} className="text-xs whitespace-normal cursor-default focus:bg-transparent" variant="destructive">
                            {overlap?.conflict_description || "Unknown conflict"}
                          </DropdownMenuItem>
                        ))
                      : (
                        <>
                          <DropdownMenuItem className="text-xs cursor-default focus:bg-transparent">
                            {issueCount} gap{issueCount !== 1 ? "s" : ""} in schedule.{" "}
                            {defaultPageId
                              ? <>Default: <span className="font-medium">{getPageName(defaultPageId)}</span></>
                              : <span className="text-muted-foreground">No default page set.</span>}
                          </DropdownMenuItem>
                          {validation?.gaps && validation.gaps.length > 0 && (
                            <>
                              <DropdownMenuSeparator />
                              {validation.gaps.map((gap, i) => {
                                if (!gap?.days || !gap?.start_time || !gap?.end_time) return null;
                                return (
                                  <DropdownMenuItem key={i} className="text-xs cursor-default focus:bg-transparent">
                                    <span className="text-muted-foreground mr-2">{formatDaysCompact(gap.days)}</span>
                                    {gap.start_time} – {gap.end_time}
                                  </DropdownMenuItem>
                                );
                              })}
                            </>
                          )}
                        </>
                      )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}

              <Button variant="brand" size="sm" onClick={handleAdd} className="btn-lift">
                <Plus className="h-4 w-4 mr-1" />
                Add Schedule
              </Button>
            </div>
          }
        />
      </TooltipProvider>

      {/* ── Location warning (sun schedules without location configured) ── */}
      {hasSunSchedules && !locationConfigured && (
        <div className="flex items-start gap-2.5 rounded-md border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-3.5 py-2.5 text-sm text-amber-800 dark:text-amber-300 flex-shrink-0">
          <MapPin className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            One or more schedules use sunrise/sunset times, but no location is configured — showing fallback times instead.{" "}
            <Link href="/settings" className="font-medium underline underline-offset-2 hover:no-underline">
              Configure location in Settings
            </Link>
            .
          </span>
        </div>
      )}

      {/* ── Schedule View ── */}
      {viewMode === "list" ? (
        <ScheduleListView
          schedules={schedules}
          pages={pages}
          carousels={carouselsData?.carousels}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />
      ) : (
        /* Calendar card: grows to fill remaining space in the pinned layout */
        <Card className="flex-1 min-h-0 flex flex-col overflow-hidden animate-card-fade-in" style={{ animationDelay: "300ms" }}>
          <CardHeader className="flex-shrink-0 py-3">
            <CardTitle className="text-base">Schedule Calendar</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 min-h-0 overflow-hidden pt-0">
            <ScheduleCalendarView
              schedules={schedules}
              pages={pages}
              carousels={carouselsData?.carousels}
              overlaps={validation?.overlaps}
              onEventClick={handleEventClick}
              onSlotSelect={handleSlotSelect}
              onEventTimeChange={handleEventTimeChange}
            />
          </CardContent>
        </Card>
      )}

        {/* Form Tray */}
        <Sheet open={showForm} onOpenChange={(open) => { if (!open) handleCloseForm(); }}>
          <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
            <SheetHeader>
              <SheetTitle>{editingSchedule ? "Edit" : "Add"} Schedule</SheetTitle>
              <SheetDescription>
                {editingSchedule ? "Update the schedule entry details" : "Create a new schedule entry"}
              </SheetDescription>
            </SheetHeader>
            {pagesData && (
              <ScheduleEntryForm
                schedule={editingSchedule || undefined}
                pages={pagesData.pages.map((p) => ({ id: p.id, name: p.name }))}
                carousels={carouselsData?.carousels}
                onSubmit={handleSubmit}
                onCancel={handleCloseForm}
                onDelete={editingSchedule ? () => {
                  const id = editingSchedule.id;
                  handleCloseForm();
                  setDeleteScheduleId(id);
                } : undefined}
                prefillStartTime={prefillData?.startTime}
                prefillEndTime={prefillData?.endTime}
                prefillDayPattern={prefillData?.dayPattern}
                prefillCustomDays={prefillData?.customDays}
              />
            )}
          </SheetContent>
        </Sheet>

        {/* Delete Confirmation Dialog */}
        <AlertDialog open={!!deleteScheduleId} onOpenChange={() => setDeleteScheduleId(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Schedule</AlertDialogTitle>
              <AlertDialogDescription>
                Are you sure you want to delete this schedule? This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => deleteScheduleId && deleteSchedule.mutate(deleteScheduleId)}
              >
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
    </PageLayout>
  );
}
