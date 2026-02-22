"use client";

import { useState, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import { PagePickerDialog } from "@/components/page-picker-dialog";
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
import { Plus, AlertCircle, CheckCircle2, AlertTriangle, List, CalendarDays } from "lucide-react";
import { api, type ScheduleEntry, type ScheduleCreate, type ScheduleUpdate, type DayPattern } from "@/lib/api";
import { toast } from "sonner";
import { extractTimeFromDate, getDayNameFromDate } from "@/lib/schedule-calendar";

type ViewMode = "list" | "calendar";

const SCHEDULE_VIEW_MODE_KEY = "schedule-view-mode";

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
  const [showDefaultPageSelector, setShowDefaultPageSelector] = useState(false);
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

  // Fetch validation (scoped by board)
  const { data: validation } = useQuery({
    queryKey: ["schedules", "validation", effectiveBoardId ?? "default"],
    queryFn: () => api.validateSchedules(effectiveBoardId || undefined),
    enabled: (schedulesData?.schedules.length || 0) > 0,
  });

  // Toggle schedule mode (per board when multi-board)
  const toggleSchedule = useMutation({
    mutationFn: (enabled: boolean) => api.setScheduleEnabled(enabled, effectiveBoardId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: 'active' });
      toast.success(schedulesData?.enabled ? "Schedule mode disabled" : "Schedule mode enabled");
    },
    onError: () => {
      toast.error("Failed to toggle schedule mode");
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
      setShowDefaultPageSelector(false);
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
      <div className="min-h-screen bg-background p-4 sm:p-6 md:p-8">
        <div className="container mx-auto max-w-6xl">
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
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-6xl">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Schedule</h1>
          <p className="text-muted-foreground mt-1 text-sm sm:text-base">
            Automate page rotation based on time and day
          </p>
          <p className="text-muted-foreground text-xs mt-1">
            Times shown in: {Intl.DateTimeFormat().resolvedOptions().timeZone}
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

        {/* Schedule Mode Toggle */}
        <Card className="mb-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Schedule Mode</CardTitle>
                <CardDescription>
                  {scheduleEnabled
                    ? "Pages automatically rotate based on schedule"
                    : "Pages are controlled manually"}
                </CardDescription>
              </div>
              <Switch
                checked={scheduleEnabled}
                onCheckedChange={toggleSchedule.mutate}
                disabled={toggleSchedule.isPending}
              />
            </div>
          </CardHeader>
        </Card>

        {/* Validation Status */}
        {scheduleEnabled && (hasOverlaps || hasGaps) && (
          <Alert 
            variant={hasOverlaps ? "destructive" : "default"} 
            className={`mb-6 ${hasGaps && !hasOverlaps && defaultPageId ? "border-blue-500/50 bg-blue-500/10" : ""}`}
          >
            {hasOverlaps ? (
              <AlertCircle className="h-4 w-4" />
            ) : hasGaps && defaultPageId ? (
              <CheckCircle2 className="h-4 w-4 text-blue-500" />
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
                      <span className="text-blue-600 dark:text-blue-400">
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

        {/* Default Page */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">Default Page</CardTitle>
            <CardDescription>
              Page to display when no schedule matches (gaps)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-sm">
                {defaultPageId ? (
                  <Badge variant="secondary">{getPageName(defaultPageId)}</Badge>
                ) : (
                  <span className="text-muted-foreground">No default page set</span>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowDefaultPageSelector(true)}
              >
                Change
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* View Toggle */}
        <div className="flex items-center justify-center sm:justify-start mb-4">
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
            onEdit={handleEdit}
            onDelete={handleDelete}
            onAdd={handleAdd}
          />
        ) : (
          <Card className="mb-6">
            <CardHeader>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <CardTitle className="text-lg">Schedule Calendar</CardTitle>
                <Button size="sm" onClick={handleAdd} className="w-full sm:w-auto">
                  <Plus className="h-4 w-4 mr-1" />
                  Add Schedule
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <ScheduleCalendarView
                schedules={schedules}
                pages={pages}
                overlaps={validation?.overlaps}
                onEventClick={handleEventClick}
                onSlotSelect={handleSlotSelect}
                onEventTimeChange={handleEventTimeChange}
              />
            </CardContent>
          </Card>
        )}

        {/* Form Dialog */}
        {showForm && pagesData && (
          <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
            <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              <CardHeader>
                <CardTitle>{editingSchedule ? "Edit" : "Add"} Schedule</CardTitle>
              </CardHeader>
              <CardContent>
                <ScheduleEntryForm
                  schedule={editingSchedule || undefined}
                  pages={pagesData.pages.map((p) => ({ id: p.id, name: p.name }))}
                  onSubmit={handleSubmit}
                  onCancel={handleCloseForm}
                  prefillStartTime={prefillData?.startTime}
                  prefillEndTime={prefillData?.endTime}
                  prefillDayPattern={prefillData?.dayPattern}
                  prefillCustomDays={prefillData?.customDays}
                />
              </CardContent>
            </Card>
          </div>
        )}

        {/* Default Page Selector Dialog */}
        {showDefaultPageSelector && pagesData && (
          <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
            <Card className="w-full max-w-md">
              <CardHeader>
                <CardTitle>Set Default Page</CardTitle>
                <CardDescription>
                  This page will display during schedule gaps
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PagePickerDialog
                  pages={pagesData.pages}
                  selectedPageId={defaultPageId || null}
                  onSelect={(pageId) => {
                    setDefaultPage.mutate(pageId);
                  }}
                  allowNone={true}
                />
                <div className="flex justify-end gap-2 mt-4">
                  <Button
                    variant="outline"
                    onClick={() => setShowDefaultPageSelector(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

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
