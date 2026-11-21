import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  BoardIcon,
  Box,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Flex,
  Heading,
  Label,
  PageCard,
  PageHeader,
  PageLayout,
  PageToolbar,
  SegmentedControl,
  SegmentedControlItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Stack,
  Switch,
  Text,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, Calendar as CalendarIcon, MapPin, Plus } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { useCurrentBoard } from "@/components/current-board-context";
import { defaultScheduleView, type ScheduleView } from "@/components/schedule/schedule-agenda";
import { ScheduleEntryAdapter as ScheduleEntryForm } from "@/components/schedule/schedule-entry-adapter";
import { ScheduleEntryConflict, useOverlapText } from "@/components/schedule/schedule-entry-conflict";
import { ScheduleWorkspace } from "@/components/schedule/schedule-workspace";
import { type ScheduleFormHandle, useScheduleEditorBridge } from "@/components/schedule-editor-bridge-context";
import Link from "@/components/smart-link";
import { useBelowRail, useRailBreakpoint } from "@/hooks/use-below-rail";
import { queryKeys } from "@/hooks/use-board";
import { useCollections } from "@/hooks/use-board";
import { useFormatPreferences } from "@/hooks/use-format-preferences";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
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
import { orderScheduleDays } from "@/lib/schedule-overlap";
import { scheduleTimezone } from "@/lib/schedule-timezone";
import { resolveSilenceConfig } from "@/lib/silence-config";
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
        <Stack gap="4">
          <Skeleton className="h-96 w-full" />
        </Stack>
      }
    >
      <ScheduleCalendarViewLazy {...props} />
    </Suspense>
  );
}

type ViewMode = ScheduleView;

function subscribeScheduleWidth(onChange: () => void) {
  window.addEventListener("resize", onChange);
  return () => window.removeEventListener("resize", onChange);
}
function scheduleWidth() {
  return window.innerWidth;
}

const SCHEDULE_VIEW_MODE_KEY = "schedule-view-mode";

/** Pre-fill for the entry form, from a calendar slot, the AI drawer, or the URL. */
interface PrefillData {
  startTime?: string;
  endTime?: string;
  dayPattern?: DayPattern;
  customDays?: string[];
  pageId?: string;
}

/**
 * Read the `prefill_*` query params the AI drawer sets when it navigates here
 * from another page. Returns null when there is nothing to prefill.
 */
function readUrlPrefill(searchParams: URLSearchParams): PrefillData | null {
  const pageId = searchParams.get("prefill_page_id");
  const startTime = searchParams.get("prefill_start");
  if (!pageId && !startTime) return null;

  const rawDayPattern = searchParams.get("prefill_days");
  const dayPattern: DayPattern | undefined =
    rawDayPattern === "all" ||
    rawDayPattern === "weekdays" ||
    rawDayPattern === "weekends" ||
    rawDayPattern === "custom"
      ? rawDayPattern
      : undefined;

  return {
    pageId: pageId ?? undefined,
    startTime: startTime ?? undefined,
    endTime: searchParams.get("prefill_end") ?? undefined,
    dayPattern,
  };
}
const NO_DEFAULT_PAGE = "__none__";

export default function SchedulePage() {
  const railBreakpoint = useRailBreakpoint();
  const t = useTranslations("schedule");
  const tCommon = useTranslations("common");
  const tAgenda = useTranslations("schedule.agenda");
  const tDays = useTranslations("daySelector");
  const belowRail = useBelowRail();
  const queryClient = useQueryClient();

  // The breakpoint chooses a default until the reader explicitly chooses a view.
  const [preferredView, setPreferredView] = useState<ViewMode | null>(() => {
    const saved = typeof window === "undefined" ? null : localStorage.getItem(SCHEDULE_VIEW_MODE_KEY);
    return saved === "list" || saved === "calendar" || saved === "day" ? saved : null;
  });
  const width = useSyncExternalStore(subscribeScheduleWidth, scheduleWidth, () => 900);
  // A phone shows the Day agenda only (07d draws Day and the entry sheet at
  // 390; a seven-column week is unreadable there, BB-C-4).
  const viewMode = belowRail ? "day" : (preferredView ?? defaultScheduleView(width));
  const setViewMode = (value: ViewMode) => {
    setPreferredView(value);
    localStorage.setItem(SCHEDULE_VIEW_MODE_KEY, value);
  };
  // Handle URL params set by the AI drawer when navigating from outside. Read
  // once, in a state initializer rather than a mount effect: the effect version
  // rendered the page without the form and then popped it open
  // (react-hooks/set-state-in-effect, issue #1568).
  const router = useRouter();
  const searchParams = useSearchParams();
  const [urlPrefill] = useState(() => readUrlPrefill(searchParams));

  const [showForm, setShowForm] = useState(urlPrefill !== null);
  const [editingSchedule, setEditingSchedule] = useState<ScheduleEntry | null>(null);
  const [deleteScheduleId, setDeleteScheduleId] = useState<string | null>(null);
  const deleteRevision = useRef<string | undefined>(undefined);

  // Board selection is shared app-wide via the sidebar selector so Schedule and
  // Dashboard stay in sync and the choice persists across reloads (#1248).
  const { currentBoardId, currentBoard, boards } = useCurrentBoard();
  // Single-board installs hit the unscoped (default-board) endpoints exactly as
  // before; only multi-board installs scope requests by the selected board id.
  const effectiveBoardId = boards.length > 1 ? currentBoardId || undefined : undefined;

  // Pre-fill data when creating from calendar slot selection or AI navigation
  const [prefillData, setPrefillData] = useState<PrefillData | null>(urlPrefill);

  // Register with the schedule editor bridge so the AI drawer can open the
  // form directly when the user is already on this page.
  const { register, unregister } = useScheduleEditorBridge();
  // A fresh key per walkthrough-opened form so nothing from a previous
  // edit lingers in the fields.
  const [formInstance, setFormInstance] = useState(0);
  const formRef = useRef<ScheduleFormHandle | null>(null);

  useEffect(() => {
    register({
      openEmpty: () => {
        setEditingSchedule(null);
        setPrefillData(null);
        setFormInstance((n) => n + 1);
        setShowForm(true);
      },
      openEntry: (scheduleId) => {
        // The list query is declared further down; read the cache instead.
        const entry = queryClient
          .getQueriesData<{ schedules?: ScheduleEntry[] }>({ queryKey: ["schedules"] })
          .flatMap(([, data]) => data?.schedules ?? [])
          .find((s) => s.id === scheduleId);
        if (!entry) return;
        setEditingSchedule(entry);
        setPrefillData(null);
        setFormInstance((n) => n + 1);
        setShowForm(true);
      },
      close: () => {
        setShowForm(false);
        setEditingSchedule(null);
        setPrefillData(null);
      },
      getForm: () => formRef.current,
    });
    return () => unregister();
  }, [register, unregister, queryClient]);

  // The AI drawer navigates here with prefill_* query params. `urlPrefill` was
  // read in the state initializer above; all that is left is scrubbing the
  // params from the URL, which has to stay in an effect because navigating
  // during render is not allowed.
  useEffect(() => {
    if (urlPrefill) {
      router.replace("/schedule", { scroll: false });
    }
  }, [urlPrefill, router]);

  // Fetch schedules (scoped by board when multi-board). keepPreviousData holds
  // the outgoing board's list on screen while the new board's loads, so
  // switching boards plays the slide transition instead of collapsing the
  // whole page to a skeleton and replaying its entrance animation.
  const { data: schedulesData, isLoading } = useQuery({
    queryKey: ["schedules", effectiveBoardId ?? "default"],
    queryFn: () => api.getSchedules(effectiveBoardId || undefined),
    placeholderData: keepPreviousData,
  });

  // Fetch pages for form
  const { data: pagesData } = useQuery({
    queryKey: ["pages"],
    queryFn: api.getPages,
  });

  // Fetch collections for form
  const { data: collectionsData } = useCollections();
  const describeOverlap = useOverlapText(pagesData?.pages ?? [], collectionsData?.collections ?? []);
  const { formatTime } = useFormatPreferences();

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
    placeholderData: keepPreviousData,
  });

  // Fetch silence schedule + user timezone so we can render the silence window
  // as a read-only overlay on the calendar/list views. Reuses the same query
  // key as the settings page so a save there refreshes both pages.
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const timezoneInfo = scheduleTimezone(allSettings?.general?.timezone);
  const timezone = timezoneInfo.zone;
  const resolvedSilenceSchedule = useMemo<ResolvedSilenceSchedule | null>(() => {
    // Silence settings are board-scoped even for single-board installs.
    const config = resolveSilenceConfig(allSettings?.silence_schedule?.config, currentBoardId || undefined);
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
  }, [allSettings, currentBoardId, timezone]);

  const handleSilenceClick = useCallback(() => {
    router.push("/settings?section=scheduling#silence-schedule");
  }, [router]);

  // Toggle schedule (per board when multi-board)
  const toggleSchedule = useMutation({
    mutationFn: (enabled: boolean) => api.setScheduleEnabled(enabled, effectiveBoardId || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
      toast.success(schedulesData?.enabled ? t("toastScheduleDisabled") : t("toastScheduleEnabled"));
    },
    onError: () => {
      toast.error(t("toastToggleFailed"));
    },
  });

  // BB-C-1: a save that leaves the entry overlapping another one is not a
  // plain success. Ask the hub (after the write) and say which entry shows.
  const announceSaved = async (saved: ScheduleEntry, savedMessage: string) => {
    try {
      const { overlaps } = await api.validateSchedules(effectiveBoardId || undefined);
      const mine = overlaps.filter((item) => item.schedule1_id === saved.id || item.schedule2_id === saved.id);
      if (mine.length) {
        const entries = [...(schedulesData?.schedules ?? []).filter((entry) => entry.id !== saved.id), saved];
        toast.warning(t("toastSavedWithOverlap"), {
          description: mine.map((item) => describeOverlap(item, saved.id, entries)).join(" "),
          duration: 10000,
        });
        return;
      }
    } catch {
      // The write succeeded; an unreachable check must not turn it into an error.
    }
    toast.success(savedMessage);
  };

  // Create schedule (include board_id when multi-board)
  const createSchedule = useMutation({
    mutationFn: (data: ScheduleCreate) =>
      api.createSchedule({ ...data, ...(effectiveBoardId && { board_id: effectiveBoardId }) }),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
      void announceSaved(saved, t("toastCreated"));
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
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
      void announceSaved(saved, t("toastUpdated"));
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
    mutationFn: (id: string) =>
      deleteRevision.current ? api.deleteSchedule(id, deleteRevision.current) : api.deleteSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
      toast.success(t("toastDeleted"));
      setDeleteScheduleId(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || t("toastDeleteFailed"));
    },
  });

  // Set default page (per board when multi-board)
  const setDefaultPage = useMutation({
    mutationFn: (pageId: string | null) => {
      const revision =
        schedulesData?.default_page_edit_protocol === "schedule-default-revision-v1"
          ? schedulesData.default_page_revision
          : undefined;
      return revision
        ? api.setDefaultPage(pageId, effectiveBoardId || undefined, revision)
        : api.setDefaultPage(pageId, effectiveBoardId || undefined);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
      toast.success(t("toastDefaultPageUpdated"));
    },
    onError: (error: Error) => {
      toast.error(error.message || t("toastDefaultPageFailed"));
    },
  });

  const handleSubmit = async (data: ScheduleCreate | ScheduleUpdate) => {
    if (editingSchedule) {
      await updateSchedule.mutateAsync({
        id: editingSchedule.id,
        data: {
          ...data,
          ...(editingSchedule.edit_protocol === "schedule-revision-v1" && editingSchedule.revision
            ? { expected_revision: editingSchedule.revision }
            : {}),
        },
      });
    } else {
      await createSchedule.mutateAsync(data as ScheduleCreate);
    }
  };

  const handleRepair = async (entry: ScheduleEntry, startTime: string) => {
    const boardId = entry.board_id || currentBoardId || undefined;
    const invalidate = () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage() });
    };
    try {
      const changed = await api.updateSchedule(entry.id, {
        start_time: startTime,
        board_id: boardId,
        ...(entry.edit_protocol === "schedule-revision-v1" && entry.revision
          ? { expected_revision: entry.revision }
          : {}),
      });
      invalidate();
      toast.success(tAgenda("repaired"), {
        duration: 6000,
        action: {
          label: tAgenda("undo"),
          onClick: async () => {
            try {
              await api.updateSchedule(entry.id, {
                start_time: entry.start_time,
                board_id: boardId,
                ...(changed.edit_protocol === "schedule-revision-v1" && changed.revision
                  ? { expected_revision: changed.revision }
                  : {}),
              });
              invalidate();
            } catch (error) {
              toast.error(error instanceof Error ? error.message : tAgenda("repairFailed"));
            }
          },
        },
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : tAgenda("repairFailed"));
    }
  };

  const handleEdit = useCallback((schedule: ScheduleEntry) => {
    setEditingSchedule(schedule);
    setPrefillData(null);
    setShowForm(true);
  }, []);

  const handleDelete = useCallback(
    (id: string) => {
      const schedule = schedulesData?.schedules.find((entry) => entry.id === id);
      deleteRevision.current = schedule?.edit_protocol === "schedule-revision-v1" ? schedule.revision : undefined;
      setDeleteScheduleId(id);
    },
    [schedulesData],
  );

  const toggleScheduleEnabled = useMutation({
    mutationFn: ({ id, enabled, revision }: { id: string; enabled: boolean; revision?: string }) =>
      api.updateSchedule(id, { enabled, ...(revision ? { expected_revision: revision } : {}) }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["schedules"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["schedules", "validation"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
      toast.success(variables.enabled ? t("toastEntryEnabled") : t("toastEntryDisabled"));
    },
    onError: (error: Error) => {
      toast.error(error.message || t("toastUpdateFailed"));
    },
  });

  const handleToggleEnabled = useCallback(
    (schedule: ScheduleEntry, enabled: boolean) => {
      toggleScheduleEnabled.mutate({
        id: schedule.id,
        enabled,
        revision: schedule.edit_protocol === "schedule-revision-v1" ? schedule.revision : undefined,
      });
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

    return orderScheduleDays(days)
      .map((d) => tDays(`dayLabels.${d}`))
      .join(", ");
  };

  // The entry sheet's subtitle names the display and when the entry repeats,
  // as 07d's sheet does ("Kitchen board · repeats on weekends", 322:20318).
  const entrySummary = (entry: ScheduleEntry) => {
    const days: Record<string, string[]> = {
      all: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
      weekdays: ["monday", "tuesday", "wednesday", "thursday", "friday"],
      weekends: ["saturday", "sunday"],
    };
    const repeat =
      entry.recurrence_type === "annual_date"
        ? t("scheduleEntryForm.recurrenceAnnual")
        : entry.recurrence_type === "one_off_date"
          ? t("scheduleEntryForm.recurrenceOneOff")
          : formatDaysCompact(entry.day_pattern === "custom" ? (entry.custom_days ?? []) : days[entry.day_pattern]);
    return [currentBoard?.name, repeat].filter(Boolean).join(" · ") || t("editScheduleDescription");
  };

  if (isLoading) {
    return (
      <PageLayout railBreakpoint={railBreakpoint}>
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
  const modeSwitch = (
    <Switch
      id="schedule-mode"
      data-testid="schedule-enabled-toggle"
      checked={scheduleEnabled}
      disabled={toggleSchedule.isPending}
      onCheckedChange={(enabled) => toggleSchedule.mutate(enabled)}
      aria-label={scheduleEnabled ? t("disableScheduleMode") : t("enableScheduleMode")}
      {...anchorProps("schedule.mode")}
    />
  );
  const addButton = (
    <Button variant="brand" size="sm" onClick={handleAdd} className="btn-lift" {...anchorProps("schedule.add")}>
      <Plus className="h-4 w-4 mr-1" />
      {t("addSchedule")}
    </Button>
  );
  const issueCount = hasOverlaps ? (validation?.overlaps?.length ?? 0) : (validation?.gaps?.length ?? 0);
  // BB-C-2: conflicts no longer hide gaps; the badge names both.
  const issueLabel = [
    hasOverlaps && t("conflictsCountTooltip", { count: validation?.overlaps?.length ?? 0 }),
    hasGaps && t("gapsCountTooltip", { count: validation?.gaps?.length ?? 0 }),
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <PageLayout railBreakpoint={railBreakpoint}>
      <Box>
        {/* ── Page header ── On a phone, 07d's Schedule · Day (322:19169): the
            title with Add beside it, then one Schedule Mode row (BB-C-3). */}
        {belowRail ? (
          <Stack gap="3" className="flex-shrink-0 pb-3 pt-2">
            <Flex align="center" justify="between" gap="3">
              <Heading level={1} size="3xl">
                {t("title")}
              </Heading>
              {addButton}
            </Flex>
            <Flex align="center" justify="between" gap="3">
              <Label htmlFor="schedule-mode">
                {tAgenda("mode")}
                {currentBoard?.name && (
                  <Text as="span" data-testid="active-board-indicator">
                    {` · ${currentBoard.name}`}
                  </Text>
                )}
              </Label>
              {modeSwitch}
            </Flex>
          </Stack>
        ) : (
          <PageHeader
            icon={CalendarIcon}
            title={t("title")}
            className={cn(
              "flex-shrink-0",
              // In calendar mode the grid wants every vertical pixel — compact the
              // header chrome on mobile so the calendar isn't squeezed.
              isCalendarMode && "py-2 sm:py-4 mb-2 sm:mb-5",
            )}
            description={t("descriptionWithTimezone", { timezone })}
          />
        )}

        {/* ── Compact toolbar: everything in one row ── */}
        <TooltipProvider>
          <PageToolbar
            className="flex-shrink-0"
            left={
              !belowRail && (
                <SegmentedControl
                  aria-label={tAgenda("view")}
                  value={viewMode}
                  onValueChange={(value) => {
                    if (value === "day" || value === "list" || value === "calendar") setViewMode(value);
                  }}
                >
                  <SegmentedControlItem value="day">{tAgenda("day")}</SegmentedControlItem>
                  <SegmentedControlItem value="calendar">{tAgenda("week")}</SegmentedControlItem>
                  <SegmentedControlItem value="list">{tAgenda("list")}</SegmentedControlItem>
                </SegmentedControl>
              )
            }
            right={
              <Flex align="center" justify="end" gap="2" wrap>
                {/* Active board indicator (multi-board only). Read-only: switching
                  boards happens via the shared sidebar selector (#1248). */}
                {!belowRail && boards.length > 1 && (
                  <Flex
                    data-testid="active-board-indicator"
                    align="center"
                    gap="1.5"
                    className="h-8 px-2.5 rounded-md border bg-muted/40 text-xs text-muted-foreground max-w-[150px]"
                  >
                    <BoardIcon className="h-3.5 w-3.5 shrink-0" />
                    <Text as="span" size="xs" tone="muted" className="truncate">
                      {currentBoard?.name || t("boardFallback", { id: currentBoardId.slice(0, 8) })}
                    </Text>
                  </Flex>
                )}

                {!belowRail && (
                  <Flex align="center" gap="2">
                    <Label htmlFor="schedule-mode">{tAgenda("mode")}</Label>
                    {modeSwitch}
                  </Flex>
                )}

                {/* Default page for gaps */}
                <Select
                  value={defaultPageId || NO_DEFAULT_PAGE}
                  onValueChange={(value) => setDefaultPage.mutate(value === NO_DEFAULT_PAGE ? null : value)}
                >
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SelectTrigger
                        {...anchorProps("schedule.default-page")}
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
                            aria-label={issueLabel}
                            className={`relative h-8 w-8 p-0 ${hasOverlaps ? "text-destructive hover:text-destructive" : "text-warning hover:text-warning"}`}
                          >
                            {hasOverlaps ? <AlertCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                            <Flex
                              align="center"
                              justify="center"
                              inline
                              className={cn(
                                "absolute -top-1 -right-1 h-4 min-w-4 px-0.5 text-xs font-bold rounded-full",
                                hasOverlaps
                                  ? "bg-destructive text-destructive-foreground"
                                  : "bg-warning text-warning-foreground",
                              )}
                            >
                              {issueCount}
                            </Flex>
                          </Button>
                        </DropdownMenuTrigger>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">{issueLabel}</TooltipContent>
                    </Tooltip>
                    <DropdownMenuContent align="end" className="w-80">
                      {hasOverlaps && (
                        <>
                          <DropdownMenuLabel className="text-destructive">
                            {t("scheduleConflictsLabel")}
                          </DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          {validation?.overlaps?.map((overlap, i) => (
                            <DropdownMenuItem
                              key={i}
                              className="text-xs whitespace-normal cursor-default focus:bg-transparent"
                              variant="destructive"
                            >
                              {describeOverlap(overlap, null, schedules) || t("unknownConflict")}
                            </DropdownMenuItem>
                          ))}
                        </>
                      )}
                      {hasOverlaps && hasGaps && <DropdownMenuSeparator />}
                      {hasGaps && (
                        <>
                          <DropdownMenuLabel className="text-warning">{t("scheduleGapsLabel")}</DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-xs cursor-default focus:bg-transparent">
                            {t("gapsInSchedule", { count: validation?.gaps?.length ?? 0 })}{" "}
                            {defaultPageId ? (
                              <>
                                {t("defaultLabel")}{" "}
                                <Text as="span" size="xs" weight="medium">
                                  {getPageName(defaultPageId)}
                                </Text>
                              </>
                            ) : (
                              <Text as="span" size="xs" tone="muted">
                                {t("noDefaultPageSet")}
                              </Text>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {validation?.gaps?.map((gap, i) => {
                            if (!gap?.days || !gap?.start_time || !gap?.end_time) return null;
                            return (
                              <DropdownMenuItem key={i} className="text-xs cursor-default focus:bg-transparent">
                                <Text as="span" size="xs" tone="muted" className="mr-2">
                                  {formatDaysCompact(gap.days)}
                                </Text>
                                {formatTime(gap.start_time)} – {formatTime(gap.end_time)}
                              </DropdownMenuItem>
                            );
                          })}
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}

                {!belowRail && addButton}
              </Flex>
            }
          />
        </TooltipProvider>

        {/* ── Location warning (sun schedules without location configured) ── */}
        {hasSunSchedules && !locationConfigured && (
          <Flex
            align="start"
            gap="2.5"
            className="rounded-md border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-3.5 py-2.5 text-sm text-amber-800 dark:text-amber-300 flex-shrink-0"
          >
            <MapPin className="h-4 w-4 mt-0.5 shrink-0" />
            <Text as="span" tone="warning">
              {t("locationWarning")}{" "}
              <Link href="/settings" className="font-medium underline underline-offset-2 hover:no-underline">
                {t("configureLocationLink")}
              </Link>
              .
            </Text>
          </Flex>
        )}

        <Box className="mt-5" {...anchorProps("schedule.root")}>
          {allSettings ? (
            <>
              {timezoneInfo.fallback && (
                <Text role="status" size="sm" tone="muted">
                  {t("lookup.timezoneFallback")}
                </Text>
              )}
              <ScheduleWorkspace
                key={`${effectiveBoardId ?? "default"}:${timezone}`}
                view={viewMode}
                compact={belowRail}
                schedules={schedules}
                pages={pages}
                collections={collectionsData?.collections ?? []}
                boardId={effectiveBoardId}
                boardName={currentBoard?.name}
                timezone={timezone}
                defaultPageId={defaultPageId}
                gaps={validation?.gaps}
                overlaps={validation?.overlaps}
                silenceSchedule={resolvedSilenceSchedule}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onToggleEnabled={handleToggleEnabled}
                onRepair={handleRepair}
                onSilenceClick={handleSilenceClick}
                onCreate={handleSlotSelect}
                legacyCalendar={
                  <Box className="h-[36rem]">
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
                  </Box>
                }
              />
            </>
          ) : (
            <Skeleton className="h-64 w-full" />
          )}
        </Box>
      </Box>

      {/* Form Tray */}
      <Sheet
        open={showForm}
        onOpenChange={(open) => {
          if (!open) handleCloseForm();
        }}
      >
        <SheetContent
          side={belowRail ? "bottom" : "right"}
          grabber={belowRail}
          // A side sheet runs the full height (a 90dvh cap left it short of the bottom in landscape, BB-C-5).
          className={belowRail ? "w-full max-h-[90dvh]" : "w-full sm:max-w-xl overflow-y-auto"}
          {...anchorProps("schedule.form")}
        >
          <SheetHeader>
            <SheetTitle>{editingSchedule ? t("editScheduleTitle") : t("addScheduleTitle")}</SheetTitle>
            <SheetDescription>
              {editingSchedule ? entrySummary(editingSchedule) : t("addScheduleDescription")}
            </SheetDescription>
          </SheetHeader>
          {pagesData && (
            <ScheduleEntryForm
              key={formInstance}
              ref={formRef}
              layout={belowRail ? "compact" : "default"}
              schedule={editingSchedule || undefined}
              pages={pagesData.pages}
              collections={collectionsData?.collections}
              onSubmit={handleSubmit}
              onCancel={handleCloseForm}
              onDelete={
                editingSchedule
                  ? () => {
                      const id = editingSchedule.id;
                      deleteRevision.current =
                        editingSchedule.edit_protocol === "schedule-revision-v1" ? editingSchedule.revision : undefined;
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
              notice={(draft) => (
                <ScheduleEntryConflict
                  draft={draft}
                  editingId={editingSchedule?.id}
                  boardId={effectiveBoardId}
                  schedules={schedulesData?.schedules ?? []}
                  pages={pagesData.pages}
                  collections={collectionsData?.collections ?? []}
                  onFix={(field, time) => formRef.current?.setField(field, time)}
                />
              )}
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
