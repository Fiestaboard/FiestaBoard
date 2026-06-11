import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  Calendar as CalendarIcon,
  CalendarDays,
  List,
  MapPin,
  Plus,
  Power,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { PageToolbar } from "@/components/page-toolbar";
import { ScheduleListView } from "@/components/schedule";
import { useScheduleEditorBridge } from "@/components/schedule-editor-bridge-context";
import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import Link from "@/components/smart-link";
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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { queryKeys, useBoardSettings } from "@/hooks/use-board";
import { useCollections } from "@/hooks/use-board";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import {
  api,
  type DayPattern,
  isCollectionId,
  type ScheduleCreate,
  type ScheduleEntry,
  type ScheduleUpdate,
  type SilenceMode,
} from "@/lib/api";
import { extractTimeFromDate, getDayNameFromDate, type ResolvedSilenceSchedule } from "@/lib/schedule-calendar";
import { utcToLocalTime } from "@/lib/timezone-utils";
import { cn } from "@/lib/utils";

// Lazy load ScheduleCalendarView since it includes react-big-calendar (~150KB+)
const ScheduleCalendarViewLazy = lazy(() =>
  import("@/components/schedule").then((mod) => ({ default: mod.ScheduleCalendarView })),
);
function ScheduleCalendarView(props: React.ComponentProps<typeof ScheduleCalendarViewLazy>) {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <Skeleton className="h-96 w-full" />
        </div>
      }
    >
      <ScheduleCalendarViewLazy {...props} />
    </Suspense>
  );
}

type ViewMode = "list" | "calendar";

const SCHEDULE_VIEW_MODE_KEY = "schedule-view-mode";
const NO_DEFAULT_PAGE = "__none__";

export default function SchedulePage() {
  const t = useTranslations("schedule");
  const tCommon = useTranslations("common");
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

  // Pre-fill data when creating from calendar slot selection or AI navigation
  const [prefillData, setPrefillData] = useState<{
    startTime?: string;
    endTime?: string;
    dayPattern?: DayPattern;
    customDays?: string[];
    pageId?: string;
  } | null>(null);

  // Register with the schedule editor bridge so the AI drawer can open the
  // form directly when the user is already on this page.
  const { register, unregister } = useScheduleEditorBridge();

  useEffect(() => {
    register((prefill) => {
      setPrefillData(
        prefill
          ? {
              pageId: prefill.page_id,
              startTime: prefill.start_time,
              endTime: prefill.end_time ?? undefined,
              dayPattern: prefill.day_pattern,
              customDays: prefill.custom_days,
            }
          : null,
      );
      setShowForm(true);
    });
    return () => unregister();
  }, [register, unregister]);

  // Handle URL params set by the AI drawer when navigating from outside.
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlParamsHandled = useRef(false);
  useEffect(() => {
    if (urlParamsHandled.current) return;
    const pageId = searchParams.get("prefill_page_id");
    const startTime = searchParams.get("prefill_start");
    const endTime = searchParams.get("prefill_end");
    const rawDayPattern = searchParams.get("prefill_days");
    const dayPattern: DayPattern | undefined =
      rawDayPattern === "all" ||
      rawDayPattern === "weekdays" ||
      rawDayPattern === "weekends" ||
      rawDayPattern === "custom"
        ? rawDayPattern
        : undefined;
    if (pageId || startTime) {
      urlParamsHandled.current = true;
      setPrefillData({
        pageId: pageId ?? undefined,
        startTime: startTime ?? undefined,
        endTime: endTime ?? undefined,
        dayPattern,
      });
      setShowForm(true);
      router.replace("/schedule", { scroll: false });
    }
  }, [searchParams, router]);

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

  // Fetch collections for form
  const { data: collectionsData } = useCollections();

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

  // Fetch silence schedule + user timezone so we can render the silence window
  // as a read-only overlay on the calendar/list views. Reuses the same query
  // key as the settings page so a save there refreshes both pages.
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const resolvedSilenceSchedule = useMemo<ResolvedSilenceSchedule | null>(() => {
    const config = allSettings?.silence_schedule?.config;
    const timezone = allSettings?.general?.timezone ?? "America/Los_Angeles";
    if (!config || !config.start_time || !config.end_time) return null;
    const startLocal = utcToLocalTime(config.start_time, timezone);
    const endLocal = utcToLocalTime(config.end_time, timezone);
    if (!startLocal || !endLocal) return null;
    const rawMode = (config.mode as string | undefined) ?? "indicator";
    const mode: SilenceMode = rawMode === "freeze" || rawMode === "page" ? rawMode : "indicator";
    return {
      enabled: !!config.enabled,
      startTimeLocal: startLocal,
      endTimeLocal: endLocal,
      mode,
      indicatorText: config.indicator_text ?? null,
      pageId: config.page_id ?? null,
    };
  }, [allSettings]);

  const handleSilenceClick = useCallback(() => {
    router.push("/settings?section=behavior#silence-schedule");
  }, [router]);

  // Toggle schedule (per board when multi-board)
  const toggleSchedule = useMutation({
    mutationFn: (enabled: boolean) => api.setScheduleEnabled(enabled, effectiveBoardId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: "active" });
      toast.success(schedulesData?.enabled ? t("toastScheduleDisabled") : t("toastScheduleEnabled"));
    },
    onError: () => {
      toast.error(t("toastToggleFailed"));
    },
  });

  // Create schedule (include board_id when multi-board)
  const createSchedule = useMutation({
    mutationFn: (data: ScheduleCreate) =>
      api.createSchedule({ ...data, ...(effectiveBoardId && { board_id: effectiveBoardId }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: "active" });
      toast.success(t("toastCreated"));
      setShowForm(false);
      setPrefillData(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || t("toastCreateFailed"));
      throw error;
    },
  });

  // Update schedule
  const updateSchedule = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ScheduleUpdate }) => api.updateSchedule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: "active" });
      toast.success(t("toastUpdated"));
      setShowForm(false);
      setEditingSchedule(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || t("toastUpdateFailed"));
      throw error;
    },
  });

  // Delete schedule
  const deleteSchedule = useMutation({
    mutationFn: (id: string) => api.deleteSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: "active" });
      toast.success(t("toastDeleted"));
      setDeleteScheduleId(null);
    },
    onError: () => {
      toast.error(t("toastDeleteFailed"));
    },
  });

  // Set default page (per board when multi-board)
  const setDefaultPage = useMutation({
    mutationFn: (pageId: string | null) => api.setDefaultPage(pageId, effectiveBoardId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: "active" });
      toast.success(t("toastDefaultPageUpdated"));
    },
    onError: () => {
      toast.error(t("toastDefaultPageFailed"));
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

  const toggleScheduleEnabled = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.updateSchedule(id, { enabled }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage, refetchType: "active" });
      toast.success(variables.enabled ? t("toastEntryEnabled") : t("toastEntryDisabled"));
    },
    onError: () => {
      toast.error(t("toastUpdateFailed"));
    },
  });

  const handleToggleEnabled = useCallback(
    (schedule: ScheduleEntry, enabled: boolean) => {
      toggleScheduleEnabled.mutate({ id: schedule.id, enabled });
    },
    [toggleScheduleEnabled],
  );

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
  const handleEventClick = useCallback(
    (schedule: ScheduleEntry) => {
      handleEdit(schedule);
    },
    [handleEdit],
  );

  // Handle calendar event time change (drag/resize)
  const handleEventTimeChange = useCallback(
    (scheduleId: string, startTime: string, endTime: string | null) => {
      updateSchedule.mutate({
        id: scheduleId,
        data: { start_time: startTime, end_time: endTime },
      });
    },
    [updateSchedule],
  );

  const getPageName = (pageId: string): string => {
    if (isCollectionId(pageId)) {
      const collection = collectionsData?.collections?.find((c) => c.id === pageId);
      return collection ? `${collection.name} ${t("collectionSuffix")}` : pageId;
    }
    return pagesData?.pages.find((p) => p.id === pageId)?.name || pageId;
  };

  const formatDaysCompact = (days: string[]): string => {
    if (!days || days.length === 0) return "";

    const weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday"];
    const weekends = ["saturday", "sunday"];
    const allDays = [...weekdays, ...weekends];

    const hasAllWeekdays = weekdays.every((d) => days.includes(d));
    const hasAllWeekends = weekends.every((d) => days.includes(d));
    const hasAllDays = allDays.every((d) => days.includes(d));

    if (hasAllDays) return t("everyDay");
    if (hasAllWeekdays && days.length === 5) return t("weekdays");
    if (hasAllWeekends && days.length === 2) return t("weekends");

    return days.map((d) => d.slice(0, 3).charAt(0).toUpperCase() + d.slice(1, 3)).join(", ");
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
  const hasSunSchedules = schedules.some((s) => s.start_type !== "fixed" || s.end_type !== "fixed");
  const scheduleEnabled = schedulesData?.enabled || false;
  const hasOverlaps = (validation?.overlaps?.length || 0) > 0;
  const hasGaps = (validation?.gaps?.length || 0) > 0;

  const isCalendarMode = viewMode === "calendar";
  const issueCount = hasOverlaps ? (validation?.overlaps?.length ?? 0) : (validation?.gaps?.length ?? 0);

  return (
    <PageLayout fillHeight={isCalendarMode}>
      {/* ── Page header ── */}
      <PageHeader
        icon={CalendarIcon}
        title={t("title")}
        className="flex-shrink-0"
        description={t("descriptionWithTimezone", { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })}
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
                {t("listView")}
              </Button>
              <Button
                variant={viewMode === "calendar" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setViewMode("calendar")}
                className="px-3"
              >
                <CalendarDays className="h-4 w-4 mr-1.5" />
                {t("calendarView")}
              </Button>
            </div>
          }
          right={
            <div className="flex items-center gap-2 flex-wrap justify-end">
              {/* Board selector (multi-board only) */}
              {boards.length > 1 && (
                <Select value={selectedBoardId} onValueChange={setSelectedBoardId}>
                  <SelectTrigger
                    data-testid="board-selector"
                    className="h-8 w-[130px] text-xs"
                    aria-label={t("boardSelectorLabel")}
                  >
                    <SelectValue placeholder={t("boardSelectorLabel")} />
                  </SelectTrigger>
                  <SelectContent>
                    {boards.map((b: { id: string; name?: string }) => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.name || t("boardFallback", { id: b.id.slice(0, 8) })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              {/* Schedule on/off toggle */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    data-testid="schedule-enabled-toggle"
                    role="switch"
                    aria-checked={scheduleEnabled}
                    aria-label={scheduleEnabled ? t("disableScheduleMode") : t("enableScheduleMode")}
                    disabled={toggleSchedule.isPending}
                    onClick={() => !toggleSchedule.isPending && toggleSchedule.mutate(!scheduleEnabled)}
                    className="flex items-center gap-1.5 border rounded-md px-2.5 h-8 cursor-pointer bg-transparent text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Power className={`h-3.5 w-3.5 ${scheduleEnabled ? "text-green-500" : "text-muted-foreground"}`} />
                    <span className="text-xs font-medium">{scheduleEnabled ? tCommon("on") : tCommon("off")}</span>
                    <span
                      aria-hidden="true"
                      className={cn(
                        "inline-flex h-[1.15rem] w-8 shrink-0 items-center rounded-full border border-transparent transition-all",
                        scheduleEnabled ? "bg-primary" : "bg-input/80 dark:bg-input/80",
                        "scale-75",
                      )}
                    >
                      <span
                        className={cn(
                          "pointer-events-none block size-4 rounded-full bg-background ring-0 transition-transform",
                          scheduleEnabled ? "translate-x-[calc(100%-3px)]" : "translate-x-px",
                        )}
                      />
                    </span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {scheduleEnabled ? t("disableScheduleMode") : t("enableScheduleMode")}
                </TooltipContent>
              </Tooltip>

              {/* Default page for gaps */}
              <Select
                value={defaultPageId || NO_DEFAULT_PAGE}
                onValueChange={(value) => setDefaultPage.mutate(value === NO_DEFAULT_PAGE ? null : value)}
              >
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SelectTrigger
                      data-testid="gap-default-select"
                      className="h-8 w-[150px] text-xs"
                      aria-label={t("gapDefaultTooltip")}
                    >
                      <SelectValue placeholder={t("gapDefaultPlaceholder")} />
                    </SelectTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">{t("gapDefaultTooltip")}</TooltipContent>
                </Tooltip>
                <SelectContent>
                  <SelectItem value={NO_DEFAULT_PAGE}>{t("noDefault")}</SelectItem>
                  {pagesData?.pages.map((page) => (
                    <SelectItem key={page.id} value={page.id}>
                      {page.name}
                    </SelectItem>
                  ))}
                  {collectionsData?.collections?.map((collection) => (
                    <SelectItem key={collection.id} value={collection.id}>
                      {collection.name} {t("collectionSuffix")}
                    </SelectItem>
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
                          {hasOverlaps ? <AlertCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                          <span
                            className={`absolute -top-1 -right-1 h-4 min-w-4 px-0.5 text-[9px] font-bold rounded-full flex items-center justify-center text-white ${hasOverlaps ? "bg-destructive" : "bg-yellow-500"}`}
                          >
                            {issueCount}
                          </span>
                        </Button>
                      </DropdownMenuTrigger>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">
                      {hasOverlaps
                        ? t("conflictsCountTooltip", { count: issueCount })
                        : t("gapsCountTooltip", { count: issueCount })}
                    </TooltipContent>
                  </Tooltip>
                  <DropdownMenuContent align="end" className="w-80">
                    <DropdownMenuLabel
                      className={hasOverlaps ? "text-destructive" : "text-yellow-600 dark:text-yellow-400"}
                    >
                      {hasOverlaps ? t("scheduleConflictsLabel") : t("scheduleGapsLabel")}
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {hasOverlaps ? (
                      validation?.overlaps?.map((overlap, i) => (
                        <DropdownMenuItem
                          key={i}
                          className="text-xs whitespace-normal cursor-default focus:bg-transparent"
                          variant="destructive"
                        >
                          {overlap?.conflict_description || t("unknownConflict")}
                        </DropdownMenuItem>
                      ))
                    ) : (
                      <>
                        <DropdownMenuItem className="text-xs cursor-default focus:bg-transparent">
                          {t("gapsInSchedule", { count: issueCount })}{" "}
                          {defaultPageId ? (
                            <>
                              {t("defaultLabel")} <span className="font-medium">{getPageName(defaultPageId)}</span>
                            </>
                          ) : (
                            <span className="text-muted-foreground">{t("noDefaultPageSet")}</span>
                          )}
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
                {t("addSchedule")}
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
            {t("locationWarning")}{" "}
            <Link href="/settings" className="font-medium underline underline-offset-2 hover:no-underline">
              {t("configureLocationLink")}
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
          collections={collectionsData?.collections}
          silenceSchedule={resolvedSilenceSchedule}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onToggleEnabled={handleToggleEnabled}
          onSilenceClick={handleSilenceClick}
        />
      ) : (
        /* Calendar card: grows to fill remaining space in the pinned layout */
        <Card
          className="flex-1 min-h-0 flex flex-col overflow-hidden animate-card-fade-in"
          style={{ animationDelay: "300ms" }}
        >
          <CardHeader className="flex-shrink-0 py-3">
            <CardTitle className="text-base">{t("scheduleCalendar")}</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 min-h-0 overflow-hidden pt-0">
            <ScheduleCalendarView
              schedules={schedules}
              pages={pages}
              collections={collectionsData?.collections}
              overlaps={validation?.overlaps}
              silenceSchedule={resolvedSilenceSchedule}
              onEventClick={handleEventClick}
              onSlotSelect={handleSlotSelect}
              onEventTimeChange={handleEventTimeChange}
              onSilenceClick={handleSilenceClick}
            />
          </CardContent>
        </Card>
      )}

      {/* Form Tray */}
      <Sheet
        open={showForm}
        onOpenChange={(open) => {
          if (!open) handleCloseForm();
        }}
      >
        <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{editingSchedule ? t("editScheduleTitle") : t("addScheduleTitle")}</SheetTitle>
            <SheetDescription>
              {editingSchedule ? t("editScheduleDescription") : t("addScheduleDescription")}
            </SheetDescription>
          </SheetHeader>
          {pagesData && (
            <ScheduleEntryForm
              schedule={editingSchedule || undefined}
              pages={pagesData.pages.map((p) => ({ id: p.id, name: p.name }))}
              collections={collectionsData?.collections}
              onSubmit={handleSubmit}
              onCancel={handleCloseForm}
              onDelete={
                editingSchedule
                  ? () => {
                      const id = editingSchedule.id;
                      handleCloseForm();
                      setDeleteScheduleId(id);
                    }
                  : undefined
              }
              prefillPageId={prefillData?.pageId}
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
            <AlertDialogTitle>{t("deleteScheduleTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("deleteScheduleConfirmation")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => deleteScheduleId && deleteSchedule.mutate(deleteScheduleId)}>
              {tCommon("delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
