"use client";

import { useState, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
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
import { Plus, AlertCircle, CheckCircle2, AlertTriangle, List, CalendarDays, Calendar as CalendarIcon } from "lucide-react";
import { api, type ScheduleEntry, type ScheduleCreate, type ScheduleUpdate, type DayPattern, isCarouselId } from "@/lib/api";
import { toast } from "sonner";
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
    (scheduleId: string, startTime: string, endTime: string) => {
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
      <div className="min-h-screen bg-background overflow-x-hidden">
        <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
          <Skeleton className="h-10 w-48 mb-4" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  const schedules = schedulesData?.schedules || [];
  const pages = pagesData?.pages || [];
  const defaultPageId = schedulesData?.default_page_id;
  const scheduleEnabled = schedulesData?.enabled || false;
  const hasOverlaps = (validation?.overlaps?.length || 0) > 0;
  const hasGaps = (validation?.gaps?.length || 0) > 0;

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        {/* Header */}
        <div className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <h1 className="page-title flex items-center gap-3">
            <CalendarIcon className="h-7 w-7 text-brand-emphasis" />
            Schedule
          </h1>
          <p className="page-description">
            Automate page rotation based on time and day
            <span className="text-xs ml-2">
              (Times shown in: {Intl.DateTimeFormat().resolvedOptions().timeZone})
            </span>
          </p>
        </div>
        {/* Board selector when multiple boards */}
        {boards.length > 1 && (
          <div className="mb-6" data-testid="board-selector">
            <label className="text-sm font-medium text-muted-foreground mb-2 block">Board</label>
            {boards.length <= 3 ? (
              <div className="flex flex-wrap gap-2">
                {boards.map((b: { id: string; name?: string }) => (
                  <Button
                    key={b.id}
                    variant={selectedBoardId === b.id ? "default" : "outline"}
                    size="sm"
                    onClick={() => setSelectedBoardId(b.id)}
                  >
                    {b.name || `Board ${b.id.slice(0, 8)}`}
                  </Button>
                ))}
              </div>
            ) : (
              <Select value={selectedBoardId} onValueChange={setSelectedBoardId}>
                <SelectTrigger className="w-[220px]">
                  <SelectValue placeholder="Select a board" />
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
          </div>
        )}

        {/* Schedule Toggle + Default Page */}
        <Card className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Schedule</CardTitle>
                <CardDescription>
                  {scheduleEnabled
                    ? "Enabled — pages automatically rotate based on schedule"
                    : "Disabled — pages are controlled manually"}
                </CardDescription>
              </div>
              <Switch
                checked={scheduleEnabled}
                onCheckedChange={toggleSchedule.mutate}
                disabled={toggleSchedule.isPending}
              />
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <label className="text-sm text-muted-foreground whitespace-nowrap">
                Default page for gaps:
              </label>
              {pagesData && (
                <Select
                  value={defaultPageId || NO_DEFAULT_PAGE}
                  onValueChange={(value) => {
                    setDefaultPage.mutate(value === NO_DEFAULT_PAGE ? null : value);
                  }}
                >
                  <SelectTrigger className="w-full sm:w-[240px]">
                    <SelectValue placeholder="Select a default page" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_DEFAULT_PAGE}>None (no default)</SelectItem>
                    {pagesData.pages.map((page) => (
                      <SelectItem key={page.id} value={page.id}>
                        {page.name}
                      </SelectItem>
                    ))}
                    {carouselsData?.carousels?.map((carousel) => (
                      <SelectItem key={carousel.id} value={carousel.id}>
                        {carousel.name} (carousel)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Validation Status */}
        {(hasOverlaps || hasGaps) && (
          <Alert 
            variant={hasOverlaps ? "destructive" : "default"} 
            className={`mb-6 ${hasGaps && !hasOverlaps && defaultPageId ? "border-info/50 bg-info/10" : ""}`}
          >
            {hasOverlaps ? (
              <AlertCircle className="h-4 w-4" />
            ) : hasGaps && defaultPageId ? (
              <CheckCircle2 className="h-4 w-4 text-info" />
            ) : (
              <AlertTriangle className="h-4 w-4" />
            )}
            <AlertDescription>
              {hasOverlaps && (
                <div className="font-semibold mb-2">Schedule Conflicts Detected</div>
              )}
              {validation?.overlaps?.map((overlap, i) => (
                <div key={i} className="text-sm">
                  {overlap?.conflict_description || "Unknown conflict"}
                </div>
              ))}
              {hasGaps && !hasOverlaps && (
                <div className="text-sm space-y-2">
                  <div>
                    {validation?.gaps?.length || 0} time gap(s) in schedule.{" "}
                    {defaultPageId ? (
                      <span className="text-info">
                        Default page &quot;{getPageName(defaultPageId)}&quot; will be shown.
                      </span>
                    ) : (
                      <span>Consider setting a default page.</span>
                    )}
                  </div>
                  {validation?.gaps && validation.gaps.length > 0 && (
                    <div className="mt-2 space-y-1 text-xs opacity-90">
                      <div className="font-semibold">Time gaps:</div>
                      {validation.gaps.map((gap, i) => {
                        if (!gap?.days || !gap?.start_time || !gap?.end_time) return null;
                        
                        return (
                          <div key={i} className="pl-2">
                            • {formatDaysCompact(gap.days)}: {gap.start_time} - {gap.end_time}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </AlertDescription>
          </Alert>
        )}

        {/* View Toggle */}
        <div className="flex items-center justify-start mb-4">
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
        </div>

        {/* Schedule View - List or Calendar */}
        {viewMode === "list" ? (
          <ScheduleListView
            schedules={schedules}
            pages={pages}
            carousels={carouselsData?.carousels}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onAdd={handleAdd}
          />
        ) : (
          <Card className="mb-6 animate-card-fade-in" style={{ animationDelay: "300ms" }}>
            <CardHeader>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <CardTitle className="text-lg">Schedule Calendar</CardTitle>
                <Button variant="brand" size="sm" onClick={handleAdd} className="w-full sm:w-auto btn-lift">
                  <Plus className="h-4 w-4 mr-1" />
                  Add Schedule
                </Button>
              </div>
            </CardHeader>
            <CardContent>
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
      </div>
    </div>
  );
}
