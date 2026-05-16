"use client";

import { useEffect, useMemo, useTransition, useRef, useDeferredValue, useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { useActivePage, useSetActivePage, usePages, useBoardSettings, getEffectiveBoardColor, getEffectiveDeviceType } from "@/hooks/use-board";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Moon, ArrowLeftRight, Calendar, AlertTriangle, GalleryHorizontalEnd, Radio, X, RefreshCw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { BoardDisplay } from "@/components/board-display";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import type { SilenceStatus, Carousel } from "@/lib/api";
import { api, isCarouselId } from "@/lib/api";
import { PageGridSelector } from "@/components/page-grid-selector";
import { readLiveOutputMessage, onLiveOutputMessageChange, writeLiveOutputMessage } from "@/lib/live-output-channel";


export function ActivePageDisplay() {
  const t = useTranslations("activeDisplay");
  const _tc = useTranslations("common");
  const router = useRouter();

  // Sheet open state
  const [isSheetOpen, setIsSheetOpen] = useState(false);
  // Pre-render state - start rendering grid in background after initial mount
  const [shouldPreRender, setShouldPreRender] = useState(false);
  // Show content after animation completes
  const [showSheetContent, setShowSheetContent] = useState(false);

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
    queryKey: ["schedules", "active"],
    queryFn: () => api.getActiveSchedule(),
    refetchInterval: 60000, // Poll every minute for schedule changes
  });

  const scheduleEnabled = activeScheduleData?.schedule_enabled || false;

  // Fetch manual active page setting
  const {
    data: activePageData,
    isLoading: isLoadingActivePage
  } = useActivePage();

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

  // Fetch board settings for display type
  const { data: boardSettings } = useBoardSettings();

  // Fetch carousels for name resolution and badge display
  const { data: carouselsData } = useQuery({
    queryKey: ["carousels"],
    queryFn: api.getCarousels,
    staleTime: 5 * 60 * 1000,
  });

  // Set active page mutation
  const setActivePageMutation = useSetActivePage();

  // Get the active page ID based on mode
  const activePageId = scheduleEnabled
    ? (activeScheduleData?.page_id || null)
    : (activePageData?.page_id || null);

  const activeCarousel = useMemo(() => {
    if (!activePageId || !isCarouselId(activePageId)) return null;
    return carouselsData?.carousels?.find((c: Carousel) => c.id === activePageId) || null;
  }, [activePageId, carouselsData]);

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
        }
      });
    }
  }, [scheduleEnabled, isLoadingActivePage, isLoadingPages, activePageId, pages, setActivePageMutation]);

  // Use transition for non-urgent updates to improve perceived performance
  const [isPending, startTransition] = useTransition();
  const lastClickTimeRef = useRef<number>(0);
  const lastPageIdRef = useRef<string | null>(null);

  // Handle page selection with debouncing and optimistic updates
  const handleSelectPage = useCallback((pageId: string) => {
    if (pageId === activePageId) {
      // Close sheet if re-selecting same page
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

    // Immediately update UI optimistically, then sync with server
    // Don't wrap in startTransition - we want this to feel instant
    setActivePageMutation.mutate(pageId, {
      onSuccess: (_result) => {
        // Close the sheet after successful selection
        setIsSheetOpen(false);

        // Use startTransition for toast notifications (non-urgent)
        startTransition(() => {
          toast.success(t("toastSwitchSuccess"));
        });
      },
      onError: () => {
        toast.error(t("toastSwitchFailed"));
      }
    });
  }, [activePageId, setActivePageMutation]);

  // Get the active page for name resolution
  const activePage = useMemo(() => {
    return pages.find(p => p.id === activePageId) || null;
  }, [pages, activePageId]);

  // Get the active page name for display
  const activePageName = useMemo(() => {
    if (!activePageId && scheduleEnabled) {
      return t("scheduleGapNoDefault");
    }
    if (activeCarousel) {
      return activeCarousel.name;
    }
    return activePage?.name || "No page selected";
  }, [activePage, activePageId, scheduleEnabled, activeCarousel]);

  // Poll the actual board state from the backend cache (backend hits Vestaboard
  // at the configured interval; we just read the cached result here).
  const { data: boardState } = useQuery({
    queryKey: ["board-current-message"],
    queryFn: () => api.getBoardCurrentMessage(),
    refetchInterval: 30_000,
    staleTime: 25_000,
  });

  // Derive device type from board state dimensions, falling back to board settings
  const activeDeviceType = useMemo((): "flagship" | "note" => {
    if (boardState) {
      if (boardState.rows === 3 && boardState.cols === 15) return "note";
      return "flagship";
    }
    return getEffectiveDeviceType(boardSettings);
  }, [boardState, boardSettings]);

  // The display message: prefer live output (page editor override), then the
  // actual board state. Falls back to null (BoardDisplay shows a skeleton).
  const displayMessage = liveOutputMessage ?? boardState?.message ?? null;

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
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">{t("title")}</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (scheduleEnabled) {
                  router.push("/schedule");
                } else {
                  setIsSheetOpen(true);
                }
              }}
              className="gap-2"
            >
              {scheduleEnabled ? (
                <>
                  <Calendar className="h-4 w-4" />
                  {t("viewSchedule")}
                </>
              ) : (
                <>
                  <ArrowLeftRight className="h-4 w-4" />
                  {t("changePage")}
                </>
              )}
            </Button>
          </div>

          {/* Active page name and status */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground mt-3 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-foreground">{activePageName}</span>
            </div>
            {liveOutputMessage ? (
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
            ) : (
              <Badge variant={scheduleEnabled ? "default" : "secondary"} className="text-xs">
                {scheduleEnabled ? (
                  <>
                    <Calendar className="h-3 w-3 mr-1" />
                    Schedule Mode
                  </>
                ) : (
                  "Manual Mode"
                )}
              </Badge>
            )}
            {activeCarousel && (
              <Badge variant="outline" className="text-xs gap-1">
                <GalleryHorizontalEnd className="h-3 w-3" />
                {t("carouselBadge")}
              </Badge>
            )}
            {silenceStatus?.active && (
              <div className="flex items-center gap-1.5">
                <Moon className="h-3 w-3 text-info" aria-hidden="true" />
                <span className="text-info">{t("silenceModeActive")}</span>
              </div>
            )}
            {isOutOfSync && (
              <Badge variant="outline" className="text-xs gap-1 border-warning/50 text-warning">
                <RefreshCw className="h-3 w-3" />
                {t("updatedExternally")}
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Schedule gap warning */}
          {scheduleEnabled && !activePageId && (
            <Alert variant="default" className="border-warning/50 bg-warning/10">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <AlertDescription className="text-sm">
                {t("noPageScheduled")}{" "}
                <button
                  onClick={() => router.push("/schedule")}
                  className="underline font-medium hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {t("scheduleSettingsLink")}
                </button>
                .
              </AlertDescription>
            </Alert>
          )}

          {/* Board Frame — contain: layout style paint isolates the tile grid from
              any layout changes in ancestor elements (e.g. sidebar padding snap). */}
          <div className="flex justify-center overflow-x-hidden px-2" style={{ contain: "layout style paint" }}>
            <BoardDisplay
              message={displayMessage}
              isLoading={!boardState && !liveOutputMessage}
              size="md"
              boardType={getEffectiveBoardColor(boardSettings)}
              deviceType={activeDeviceType}
            />
          </div>
        </CardContent>
      </Card>

      {/* Pre-render grid in background (hidden) to warm up cache */}
      {shouldPreRender && !isSheetOpen && (
        <div className="hidden">
          <PageGridSelector
            activePageId={deferredActivePageId}
            onSelectPage={handleSelectPage}
            isPending={isPending || setActivePageMutation.isPending}
            showActiveIndicator={true}
            label=""
          />
        </div>
      )}

      {/* Page Selector Sheet - grid is already cached so opens instantly */}
      <Sheet open={isSheetOpen} onOpenChange={setIsSheetOpen}>
        <SheetContent side="right" className="w-full sm:max-w-4xl overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{t("selectPageTitle")}</SheetTitle>
            <SheetDescription>
              {t("selectPageDescription")}
            </SheetDescription>
          </SheetHeader>

          <div className="mt-6">
            {!showSheetContent ? (
              // Show lightweight skeleton during animation for smooth 60fps
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : shouldPreRender ? (
              <PageGridSelector
                activePageId={deferredActivePageId}
                onSelectPage={handleSelectPage}
                isPending={isPending || setActivePageMutation.isPending}
                showActiveIndicator={true}
                label=""
              />
            ) : (
              <div className="text-center text-sm text-muted-foreground py-8">
                {t("loadingPages")}
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
