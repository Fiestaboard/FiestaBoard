"use client";

import {
  Alert,
  AlertDescription,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Grid,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeftRight,
  Calendar,
  CalendarOff,
  GalleryHorizontalEnd,
  Loader2,
  Moon,
  Pause,
  Radio,
  Timer,
  UploadCloud,
  X,
} from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import { useCurrentBoard } from "@/components/current-board-context";
import { ForceSetDialog } from "@/components/force-set-dialog";
import { PageGridSelector } from "@/components/page-grid-selector";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import Link from "@/components/smart-link";
import {
  getEffectiveBoardColor,
  getEffectiveDeviceType,
  queryKeys,
  useActivePage,
  useBoardCurrentMessage,
  useBoardSettings,
  usePagePreview,
  usePages,
  useSetActivePage,
} from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { BoardCurrentMessageResponse, Collection, SilenceStatus } from "@/lib/api";
import { api, isCollectionId } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";
import { onLiveOutputMessageChange, readLiveOutputMessage, writeLiveOutputMessage } from "@/lib/live-output-channel";

export function ActivePageDisplay() {
  const t = useTranslations("activeDisplay");
  const _tc = useTranslations("common");
  const tPause = useTranslations("displaySettings.pause");

  // Current board selection (issue #1247). Queries are board-scoped only in
  // multi-board installs so single-board behavior is completely unchanged.
  const { currentBoardId, currentBoard, boards } = useCurrentBoard();
  const isMultiBoard = boards.length > 1;
  const scopedBoardId = isMultiBoard && currentBoardId ? currentBoardId : undefined;
  // Live board polling (and Live Output) only track the primary board.
  const isPrimaryBoard = !scopedBoardId || scopedBoardId === boards[0]?.id;

  // Sheet open state
  const [isSheetOpen, setIsSheetOpen] = useState(false);
  // Pre-render state - start rendering grid in background after initial mount
  const [shouldPreRender, setShouldPreRender] = useState(false);
  // Show content after animation completes
  const [showSheetContent, setShowSheetContent] = useState(false);
  // Resend-to-board loading state
  const [isSyncing, setIsSyncing] = useState(false);
  // Force-set dialog state
  const [forceSetDialogOpen, setForceSetDialogOpen] = useState(false);
  const [forceSetPageId, setForceSetPageId] = useState<string | null>(null);
  // Schedule mode choice dialog (shown before page selector when schedule is active)
  const [changeModeOpen, setChangeModeOpen] = useState(false);
  // When true, the page selector treats selection as manual (after disabling schedule)
  const [openSheetAsManual, setOpenSheetAsManual] = useState(false);

  // Start pre-rendering grid in background after component mounts
  useEffect(() => {
    // Use startTransition to make this low-priority
    const timer = setTimeout(() => {
      startTransition(() => {
        setShouldPreRender(true);
      });
    }, 500); // Wait 500ms after mount to avoid blocking initial render

    return () => clearTimeout(timer);
  }, []);

  // Handle showing content after animation completes
  useEffect(() => {
    if (isSheetOpen) {
      // Wait for slide animation to complete (400ms) before revealing content
      const timer = setTimeout(() => {
        setShowSheetContent(true);
      }, 420); // Slightly after animation (400ms + buffer)
      return () => clearTimeout(timer);
    } else {
      // Hide immediately when closing
      setShowSheetContent(false);
    }
  }, [isSheetOpen]);

  // Fetch schedule status and active page in a single request.
  // getActiveSchedule() returns both schedule_enabled and the active page_id
  // regardless of mode, eliminating the need for a separate heavyweight
  // getSchedules() call that fetched the entire schedule list.
  const { data: activeScheduleData } = useQuery({
    // Board-scoped key: the unscoped ["schedules", "active"] invalidations
    // used elsewhere still match it as a prefix.
    queryKey: scopedBoardId ? ["schedules", "active", scopedBoardId] : ["schedules", "active"],
    queryFn: () => api.getActiveSchedule(scopedBoardId),
    refetchInterval: 60000, // Poll every minute for schedule changes
  });

  const scheduleEnabled = activeScheduleData?.schedule_enabled || false;

  // Derive temporary override info from the active-schedule response (no extra API call)
  const temporaryOverride = activeScheduleData?.temporary_override ?? null;
  const overrideActive = temporaryOverride?.active === true;
  const overrideRemainingMinutes =
    overrideActive && temporaryOverride?.remaining_seconds ? Math.floor(temporaryOverride.remaining_seconds / 60) : 0;

  // Fetch manual active page setting for the selected board
  const { data: activePageData, isLoading: isLoadingActivePage } = useActivePage(scopedBoardId);

  // Fetch silence mode status to show snoozing indicator
  const { data: silenceStatus } = useQuery<SilenceStatus>({
    queryKey: ["silenceStatus"],
    queryFn: api.getSilenceStatus,
  });

  // Fetch live board state so the Home display reflects what was last sent
  // via Live Output in the page editor. The query is seeded from localStorage
  // on mount so it works across browser tabs, and a `storage` event listener
  // keeps it in sync when another tab writes a new live message.
  const queryClient = useQueryClient();
  const { data: liveOutputMessage } = useQuery<string | null>({
    queryKey: ["liveOutputMessage"],
    queryFn: () => null,
    staleTime: Infinity,
    initialData: () => readLiveOutputMessage(),
  });

  // Keep the query cache in sync with changes from other tabs.
  useEffect(() => {
    // Seed from localStorage on mount only when a live message is present
    // (i.e. another tab enabled Live Output before this tab opened).
    // We intentionally skip the null case to avoid overwriting a value that
    // the page-builder already wrote into the cache in the same tab.
    const current = readLiveOutputMessage();
    if (current !== null) {
      queryClient.setQueryData(["liveOutputMessage"], current);
    }

    return onLiveOutputMessageChange((msg) => {
      queryClient.setQueryData(["liveOutputMessage"], msg);
    });
  }, [queryClient]);

  // Turn off Live Mode from the home page. Clears the shared live-output
  // cache + localStorage (so all tabs stop showing live content) and asks the
  // backend to refresh the board back to its scheduled/manual page. This is
  // important because when the user enables Live Output in the page editor
  // and then leaves that page, the inactivity timeout is bound to that
  // component and never fires after navigation — without a kill switch here,
  // the Home page would stay stuck pulsing "Live Mode" indefinitely.
  const handleDisableLiveMode = useCallback(() => {
    queryClient.setQueryData(["liveOutputMessage"], null);
    writeLiveOutputMessage(null);
    api.forceRefresh().catch(() => {
      // Silently ignore errors — UI state is already cleared.
    });
    toast.success("Live Mode turned off");
  }, [queryClient]);

  const clearOverrideMutation = useMutation({
    mutationFn: () => api.clearTemporaryOverride(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      api.forceRefresh().catch(() => {});
      toast.success(t("toastOverrideCancelled"));
    },
    onError: () => {
      toast.error("Failed to cancel override");
    },
  });

  const disableScheduleMutation = useMutation({
    mutationFn: () => api.setScheduleEnabled(false, scopedBoardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      toast.success(t("changeModeDisableSuccess"));
      setChangeModeOpen(false);
      setOpenSheetAsManual(true);
      setIsSheetOpen(true);
    },
    onError: () => {
      toast.error("Failed to disable schedule mode");
    },
  });

  const handleResendToBoard = useCallback(async () => {
    setIsSyncing(true);
    try {
      await api.forceRefresh();
      // Optimistically mark as in-sync so the alert disappears immediately.
      // The backend schedules a ~3 s deferred board read after each send;
      // we update the cache now and do a real refetch after 4 s to confirm.
      queryClient.setQueryData(
        queryKeys.boardCurrentMessage(scopedBoardId),
        (old: BoardCurrentMessageResponse | undefined) => {
          if (!old) return old;
          return { ...old, characters: old.expected_characters ?? old.characters };
        },
      );
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.boardCurrentMessage() });
      }, 4000);
      toast.success(t("toastResendSuccess"));
    } catch {
      toast.error(t("toastResendFailed"));
    } finally {
      setIsSyncing(false);
    }
  }, [queryClient, scopedBoardId, t]);

  // Fetch board settings for display type
  const { data: boardSettings } = useBoardSettings();

  // Surface per-board paused status on Home (issue #970). When a board is
  // paused FiestaBoard does not push anything to it from any code path —
  // mirror the settings-page badge here so users aren't confused by a board
  // that appears "stuck" while paused.
  const pausedBoards = useMemo(() => (boardSettings?.boards ?? []).filter((b) => b.paused === true), [boardSettings]);
  const showBoardNameOnPauseBadge = (boardSettings?.boards?.length ?? 0) > 1;

  // Fetch collections for name resolution and badge display
  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: api.getCollections,
    staleTime: 5 * 60 * 1000,
  });

  // Set active page mutation — targets the selected board only
  const setActivePageMutation = useSetActivePage(scopedBoardId);

  // currentBoard (destructured above from useCurrentBoard()) is also used to
  // filter the page picker to size-compatible pages and to warn about
  // partially-fitting collections (issue #1249).

  // Get the active page ID based on mode
  const activePageId = scheduleEnabled ? activeScheduleData?.page_id || null : activePageData?.page_id || null;

  const activeCollection = useMemo(() => {
    if (!activePageId || !isCollectionId(activePageId)) return null;
    return collectionsData?.collections?.find((c: Collection) => c.id === activePageId) || null;
  }, [activePageId, collectionsData]);

  // Defer activePageId updates to reduce priority of non-urgent re-renders
  // This makes clicking feel more responsive
  const deferredActivePageId = useDeferredValue(activePageId);

  // Fetch all pages for default page selection and sheet display
  const { data: pagesData, isLoading: isLoadingPages } = usePages();

  // Default to first page if no active page is set (only in manual mode)
  const pages = useMemo(() => pagesData?.pages || [], [pagesData]);
  useEffect(() => {
    // Only auto-select first page in manual mode, not in schedule mode
    // In schedule mode, null activePageId means a gap with no default (intentional)
    if (!scheduleEnabled && !isLoadingActivePage && !isLoadingPages && !activePageId && pages.length > 0) {
      const firstPage = pages[0];
      setActivePageMutation.mutate(firstPage.id, {
        onSuccess: (_result) => {
          toast.success(t("toastSetActivePage", { pageName: firstPage.name }));
        },
        onError: () => {
          toast.error(t("toastSetDefaultFailed"));
        },
      });
    }
  }, [scheduleEnabled, isLoadingActivePage, isLoadingPages, activePageId, pages, setActivePageMutation]);

  // Use transition for non-urgent updates to improve perceived performance
  const [isPending, startTransition] = useTransition();
  const lastClickTimeRef = useRef<number>(0);
  const lastPageIdRef = useRef<string | null>(null);

  // Handle page selection with debouncing and optimistic updates
  const handleSelectPage = useCallback(
    (pageId: string) => {
      if (pageId === activePageId && !scheduleEnabled && !overrideActive) {
        // Close sheet if re-selecting same page in manual mode with no override
        setIsSheetOpen(false);
        return;
      }

      // Debounce rapid clicks (within 200ms) to prevent spam
      const now = Date.now();
      if (pageId === lastPageIdRef.current && now - lastClickTimeRef.current < 200) {
        return;
      }
      lastClickTimeRef.current = now;
      lastPageIdRef.current = pageId;

      if ((scheduleEnabled || overrideActive) && !openSheetAsManual) {
        // In schedule mode (or while an override is already active), show the
        // Force Set dialog so the user can pick a duration and revert mode.
        setForceSetPageId(pageId);
        setForceSetDialogOpen(true);
        setIsSheetOpen(false);
        return;
      }

      // Non-fatal size warning when a collection only partially fits the
      // current board — mirrors the backend `warnings` from #1245.
      if (currentBoard && isCollectionId(pageId)) {
        const collection = collectionsData?.collections?.find((c: Collection) => c.id === pageId);
        const members = (collection?.page_ids ?? [])
          .map((pid) => pages.find((p) => p.id === pid))
          .filter((p): p is (typeof pages)[number] => Boolean(p));
        const misfits = members.filter((p) => !pagesCompatibleWithBoard(p, currentBoard));
        if (members.length > 0 && misfits.length > 0) {
          toast.warning(t("collectionSizeWarning", { count: misfits.length, total: members.length }));
        }
      }

      // Manual mode (or after the user chose to disable schedule): switch immediately.
      setOpenSheetAsManual(false);
      setActivePageMutation.mutate(pageId, {
        onSuccess: (_result) => {
          setIsSheetOpen(false);
          startTransition(() => {
            toast.success(t("toastSwitchSuccess"));
          });
        },
        onError: () => {
          toast.error(t("toastSwitchFailed"));
        },
      });
    },
    [
      activePageId,
      scheduleEnabled,
      overrideActive,
      openSheetAsManual,
      setActivePageMutation,
      currentBoard,
      collectionsData,
      pages,
      t,
    ],
  );

  // Get the active page for name resolution
  const activePage = useMemo(() => {
    return pages.find((p) => p.id === activePageId) || null;
  }, [pages, activePageId]);

  // Get the active page name for display
  const activePageName = useMemo(() => {
    if (!activePageId && scheduleEnabled) {
      return t("scheduleGapNoDefault");
    }
    if (activeCollection) {
      return activeCollection.name;
    }
    return activePage?.name || "No page selected";
  }, [activePage, activePageId, scheduleEnabled, activeCollection]);

  // Poll the actual board state from the backend cache (backend hits Vestaboard
  // at the configured interval; we just read the cached result here). Secondary
  // boards are served from their runtime's last-sent cache (issue #1247).
  const { data: boardState } = useBoardCurrentMessage(scopedBoardId);

  // Live Output drives the primary board, so only surface it there.
  const liveMessageForBoard = isPrimaryBoard ? (liveOutputMessage ?? null) : null;

  // Graceful degrade for a secondary board with no cached content yet
  // (nothing sent since startup): render its active page instead of a blank.
  const needsPreviewFallback = !!scopedBoardId && !!boardState && boardState.message === null;
  const fallbackPageId = needsPreviewFallback && activePageId && !isCollectionId(activePageId) ? activePageId : null;
  const { data: fallbackPreview } = usePagePreview(fallbackPageId, { enabled: needsPreviewFallback });

  // Derive device type from board state dimensions, falling back to the
  // selected board's settings.
  const activeDeviceType = useMemo((): "flagship" | "note" => {
    if (boardState) {
      if (boardState.rows === 3 && boardState.cols === 15) return "note";
      return "flagship";
    }
    if (currentBoard?.device_type) return currentBoard.device_type === "note" ? "note" : "flagship";
    return getEffectiveDeviceType(boardSettings);
  }, [boardState, currentBoard, boardSettings]);

  // The display message: prefer live output (page editor override), then the
  // actual board state, then the active-page render fallback for a secondary
  // board with no cached content. Falls back to null (skeleton).
  const displayMessage = liveMessageForBoard ?? boardState?.message ?? fallbackPreview?.message ?? null;

  // Out-of-sync: the board was updated externally if its current state differs
  // from what FiestaBoard last sent.
  const isOutOfSync = useMemo(() => {
    if (!boardState?.expected_characters || !boardState?.characters) return false;
    return JSON.stringify(boardState.characters) !== JSON.stringify(boardState.expected_characters);
  }, [boardState]);

  return (
    <>
      <Card className="card-interactive">
        <CardHeader className="pb-4">
          <Flex align="center" justify="between">
            <Flex align="baseline" gap="2" className="min-w-0">
              <CardTitle className="text-lg">{t("title")}</CardTitle>
              {isMultiBoard && currentBoard && (
                <Text as="span" size="xs" tone="muted" className="truncate" data-testid="active-display-board-name">
                  {t("boardIndicator", { boardName: currentBoard.name })}
                </Text>
              )}
            </Flex>
            <Flex align="center" gap="2">
              {scheduleEnabled && (
                <Link
                  href="/schedule"
                  className="text-xs text-muted-foreground underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {t("viewSchedule")} →
                </Link>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => (scheduleEnabled ? setChangeModeOpen(true) : setIsSheetOpen(true))}
                className="gap-2"
              >
                <ArrowLeftRight className="h-4 w-4" />
                {t("changePage")}
              </Button>
            </Flex>
          </Flex>

          {/* Active page name and status */}
          <Flex align="center" gap="4" wrap className="text-xs text-muted-foreground mt-3">
            <Flex align="center" gap="1.5">
              <Text as="span" size="xs" weight="medium">
                {activePageName}
              </Text>
            </Flex>
            {liveMessageForBoard ? (
              <Badge
                variant="destructive"
                className="text-xs gap-1 animate-pulse pr-1 cursor-pointer hover:opacity-90 focus-within:ring-2 focus-within:ring-ring"
              >
                <Radio className="h-3 w-3" aria-hidden="true" />
                Live Mode
                <button
                  type="button"
                  onClick={handleDisableLiveMode}
                  aria-label="Turn off Live Mode"
                  title="Turn off Live Mode"
                  className="ml-0.5 inline-flex items-center justify-center rounded-sm hover:bg-black/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </Badge>
            ) : overrideActive ? (
              <Badge variant="outline" className="text-xs gap-1 border-primary/50 text-primary pr-1">
                <Timer className="h-3 w-3" aria-hidden="true" />
                {overrideRemainingMinutes > 0
                  ? t("overrideBadge", { minutes: overrideRemainingMinutes })
                  : t("overrideBadgeLessThan1m")}
                <button
                  type="button"
                  onClick={() => clearOverrideMutation.mutate()}
                  aria-label={t("cancelOverride")}
                  title={t("cancelOverride")}
                  disabled={clearOverrideMutation.isPending}
                  className="ml-0.5 inline-flex items-center justify-center rounded-sm hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </Badge>
            ) : (
              <Badge variant={scheduleEnabled ? "default" : "secondary"} className="text-xs">
                {scheduleEnabled ? (
                  <>
                    <Calendar className="h-3 w-3 mr-1" />
                    {t("scheduleMode")}
                  </>
                ) : (
                  t("manualMode")
                )}
              </Badge>
            )}
            {activeCollection && (
              <Badge variant="outline" className="text-xs gap-1">
                <GalleryHorizontalEnd className="h-3 w-3" />
                {t("collectionBadge")}
              </Badge>
            )}
            {silenceStatus?.active && (
              <Flex align="center" gap="1.5">
                <Moon className="h-3 w-3 text-info" aria-hidden="true" />
                <Text as="span" size="xs" tone="info">
                  {t("silenceModeActive")}
                </Text>
              </Flex>
            )}
            {pausedBoards.map((board) => (
              <Badge
                key={board.id}
                variant="default"
                className="text-xs gap-1 bg-amber-500 text-white hover:bg-amber-500"
                data-testid="board-paused-badge"
                title={tPause("tooltip")}
              >
                <Pause className="h-3 w-3" aria-hidden="true" />
                {showBoardNameOnPauseBadge ? `${tPause("badge")}: ${board.name}` : tPause("badge")}
              </Badge>
            ))}
          </Flex>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Schedule gap warning */}
          {scheduleEnabled && !activePageId && (
            <Alert variant="default" className="border-warning/50 bg-warning/10">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <AlertDescription className="text-sm">
                {t("noPageScheduled")}{" "}
                <Link
                  href="/schedule"
                  className="underline font-medium hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {t("scheduleSettingsLink")}
                </Link>
                .
              </AlertDescription>
            </Alert>
          )}

          {/* Out-of-sync warning: board was changed by another app */}
          {isOutOfSync && !liveMessageForBoard && (
            <Alert variant="default" className="border-warning/50 bg-warning/10">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <AlertDescription className="flex items-center justify-between gap-3">
                <Text as="span" size="sm">
                  {t("updatedExternally")}
                </Text>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleResendToBoard}
                  disabled={isSyncing}
                  className="shrink-0 gap-1.5 border-warning/50 text-warning hover:bg-warning/10 hover:text-warning"
                >
                  {isSyncing ? <Loader2 className="h-3 w-3 animate-spin" /> : <UploadCloud className="h-3 w-3" />}
                  {t("resendToBoard")}
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {/* Board Frame — contain: layout style paint isolates the tile grid from
              any layout changes in ancestor elements (e.g. sidebar padding snap).
              ScaledBoardDisplay shrinks the board to fit narrow (mobile) cards —
              BoardDisplay's breakpoint tile sizes alone overflow phone widths. */}
          <Flex justify="center" className="overflow-x-hidden px-2" style={{ contain: "layout style paint" }}>
            <ScaledBoardDisplay
              message={displayMessage}
              isLoading={!boardState && !liveMessageForBoard}
              size="md"
              boardType={currentBoard?.board_color ?? getEffectiveBoardColor(boardSettings)}
              deviceType={activeDeviceType}
            />
          </Flex>
        </CardContent>
      </Card>

      {/* Pre-render grid in background (hidden) to warm up cache */}
      {shouldPreRender && !isSheetOpen && (
        <Box className="hidden">
          <PageGridSelector
            activePageId={deferredActivePageId}
            onSelectPage={handleSelectPage}
            isPending={isPending || setActivePageMutation.isPending}
            showActiveIndicator={true}
            label=""
            filterByCurrentBoardSize
          />
        </Box>
      )}

      {/* Page Selector Sheet - grid is already cached so opens instantly */}
      <Sheet
        open={isSheetOpen}
        onOpenChange={(open) => {
          setIsSheetOpen(open);
          if (!open) setOpenSheetAsManual(false);
        }}
      >
        <SheetContent side="right" className="w-full sm:max-w-4xl overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{t("selectPageTitle")}</SheetTitle>
            <SheetDescription>{t("selectPageDescription")}</SheetDescription>
          </SheetHeader>

          <Box className="mt-6">
            {!showSheetContent ? (
              // Show lightweight skeleton during animation for smooth 60fps
              <Grid cols="1" sm="2" gap="3">
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
              </Grid>
            ) : shouldPreRender ? (
              <PageGridSelector
                activePageId={deferredActivePageId}
                onSelectPage={handleSelectPage}
                isPending={isPending || setActivePageMutation.isPending}
                showActiveIndicator={true}
                label=""
                filterByCurrentBoardSize
              />
            ) : (
              <Text tone="muted" className="text-center py-8">
                {t("loadingPages")}
              </Text>
            )}
          </Box>
        </SheetContent>
      </Sheet>

      {/* Force Set dialog — opened when user picks a page while in schedule mode */}
      <ForceSetDialog
        open={forceSetDialogOpen}
        onOpenChange={setForceSetDialogOpen}
        pageId={forceSetPageId}
        pageName={pages.find((p) => p.id === forceSetPageId)?.name ?? ""}
      />

      {/* Schedule mode choice dialog — shown before page selector when schedule is active */}
      <Dialog open={changeModeOpen} onOpenChange={setChangeModeOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("changeModeTitle")}</DialogTitle>
            <DialogDescription>{t("changeModeDescription")}</DialogDescription>
          </DialogHeader>

          <Stack gap="3" className="py-2">
            {/* Override temporarily */}
            <button
              type="button"
              onClick={() => {
                setChangeModeOpen(false);
                setIsSheetOpen(true);
              }}
              className="flex items-start gap-4 p-4 rounded-xl border border-border hover:border-primary/50 hover:bg-primary/5 text-left transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Flex
                align="center"
                justify="center"
                className="h-10 w-10 rounded-full bg-primary/10 flex-shrink-0 group-hover:bg-primary/20 transition-colors"
              >
                <Timer className="h-5 w-5 text-primary" />
              </Flex>
              <Box className="min-w-0">
                <Text size="sm" weight="semibold">
                  {t("changeModeOverrideTitle")}
                </Text>
                <Text size="xs" tone="muted" className="mt-0.5 leading-relaxed">
                  {t("changeModeOverrideDescription")}
                </Text>
              </Box>
            </button>

            {/* Turn off schedule */}
            <button
              type="button"
              onClick={() => disableScheduleMutation.mutate()}
              disabled={disableScheduleMutation.isPending}
              className="flex items-start gap-4 p-4 rounded-xl border border-border hover:border-muted-foreground/40 hover:bg-muted/40 text-left transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Flex
                align="center"
                justify="center"
                className="h-10 w-10 rounded-full bg-muted flex-shrink-0 group-hover:bg-muted/80 transition-colors"
              >
                {disableScheduleMutation.isPending ? (
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                ) : (
                  <CalendarOff className="h-5 w-5 text-muted-foreground" />
                )}
              </Flex>
              <Box className="min-w-0">
                <Text size="sm" weight="semibold">
                  {t("changeModeDisableTitle")}
                </Text>
                <Text size="xs" tone="muted" className="mt-0.5 leading-relaxed">
                  {t("changeModeDisableDescription")}
                </Text>
              </Box>
            </button>
          </Stack>

          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setChangeModeOpen(false)}>
              {_tc("cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
