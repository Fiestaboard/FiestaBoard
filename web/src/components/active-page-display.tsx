"use client";

import { useEffect, useMemo, useTransition, useRef, useDeferredValue, useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { useActivePage, useSetActivePage, usePagePreview, usePages, useBoardSettings, getEffectiveBoardColor, getEffectiveDeviceType } from "@/hooks/use-board";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Moon, ArrowLeftRight, Calendar, AlertTriangle, GalleryHorizontalEnd } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { BoardDisplay } from "@/components/board-display";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import type { SilenceStatus, Carousel } from "@/lib/api";
import { api, isCarouselId } from "@/lib/api";
import { PageGridSelector } from "@/components/page-grid-selector";


// Parse a line into tokens (same logic as BoardDisplay)
type Token = { type: "char"; value: string } | { type: "color"; code: string };

function parseLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  
  while (i < line.length) {
    if (line[i] === "{") {
      const closingBrace = line.indexOf("}", i);
      if (closingBrace !== -1) {
        const content = line.substring(i + 1, closingBrace);
        
        // Skip end tags {/...} or {/}
        if (content.startsWith("/")) {
          i = closingBrace + 1;
          continue;
        }
        
        // Check if it's a color code (63-70 or named colors)
        if (/^\d+$/.test(content) && parseInt(content) >= 63 && parseInt(content) <= 70) {
          tokens.push({ type: "color", code: content });
          i = closingBrace + 1;
          continue;
        }
      }
    }
    
    // Convert to uppercase since board only supports uppercase letters
    tokens.push({ type: "char", value: line[i].toUpperCase() });
    i++;
  }
  
  return tokens;
}

function tokensToString(tokens: Token[]): string {
  return tokens.map(token => {
    if (token.type === "color") {
      return `{${token.code}}`;
    }
    return token.value;
  }).join('');
}

// Add snoozing indicator to bottom right of board content
function addSnoozingIndicator(content: string, numRows: number = 6, numCols: number = 22): string {
  const lines = content.split('\n');
  
  // Ensure we have exactly numRows lines (board rows)
  while (lines.length < numRows) {
    lines.push("");
  }
  
  const lastIdx = numRows - 1;
  // Parse the last line into tokens (each token = 1 board position)
  const lastLineTokens = parseLine(lines[lastIdx] || "");
  
  // Pad to numCols tokens total
  while (lastLineTokens.length < numCols) {
    lastLineTokens.push({ type: "char", value: " " });
  }
  
  // Truncate if too long
  const boardTokens = lastLineTokens.slice(0, numCols);
  
  // For note (15 cols), use shorter "ZZZ" indicator; for flagship use "SNOOZING"
  const indicator = numCols >= 22 ? "SNOOZING" : "ZZZ";
  const startPos = numCols - indicator.length;
  for (let i = 0; i < indicator.length; i++) {
    boardTokens[startPos + i] = { type: "char", value: indicator[i] };
  }
  
  // Convert back to string
  lines[lastIdx] = tokensToString(boardTokens);
  
  return lines.slice(0, numRows).join('\n');
}

export function ActivePageDisplay() {
  const t = useTranslations("activeDisplay");
  const tc = useTranslations("common");
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
  
  // Fetch board settings for display type
  const { data: boardSettings } = useBoardSettings();

  // Fetch carousels for name resolution
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
  
  // For carousels, determine which page to preview based on current time.
  // Uses a timer so the preview cycles through pages at the carousel interval.
  const computeCarouselPageId = useCallback((carousel: Carousel | null) => {
    if (!carousel) return null;
    const nowSec = Math.floor(Date.now() / 1000);
    const idx = Math.floor(nowSec / carousel.interval_seconds) % carousel.page_ids.length;
    return carousel.page_ids[idx];
  }, []);

  const [currentCarouselPageId, setCurrentCarouselPageId] = useState<string | null>(() =>
    computeCarouselPageId(activeCarousel)
  );

  useEffect(() => {
    setCurrentCarouselPageId(computeCarouselPageId(activeCarousel));
    if (!activeCarousel) return;
    const interval = setInterval(() => {
      setCurrentCarouselPageId(computeCarouselPageId(activeCarousel));
    }, 1000);
    return () => clearInterval(interval);
  }, [activeCarousel, computeCarouselPageId]);

  // The actual page to preview: either the direct page or the carousel's current page.
  // Guard against passing a raw carousel ID to the preview endpoint while carousels are loading.
  const previewPageId = activeCarousel ? currentCarouselPageId : (isCarouselId(activePageId) ? null : activePageId);

  // Fetch preview of active page (or carousel's current page)
  const { 
    data: previewData, 
    isLoading: isLoadingPreview
  } = usePagePreview(previewPageId, { 
    enabled: !!previewPageId,
    refetchInterval: activeCarousel ? activeCarousel.interval_seconds * 1000 : undefined,
  });
  
  // Default to first page if no active page is set (only in manual mode)
  const pages = useMemo(() => pagesData?.pages || [], [pagesData]);
  useEffect(() => {
    // Only auto-select first page in manual mode, not in schedule mode
    // In schedule mode, null activePageId means a gap with no default (intentional)
    if (!scheduleEnabled && !isLoadingActivePage && !isLoadingPages && !activePageId && pages.length > 0) {
      const firstPage = pages[0];
      setActivePageMutation.mutate(firstPage.id, {
        onSuccess: (result) => {
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
      onSuccess: (result) => {
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
  
  // Get the active page for device type and name
  const activePage = useMemo(() => {
    if (activeCarousel && currentCarouselPageId) {
      return pages.find(p => p.id === currentCarouselPageId) || null;
    }
    return pages.find(p => p.id === activePageId) || null;
  }, [pages, activePageId, activeCarousel, currentCarouselPageId]);

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
  
  // Get active page device type, falling back to the board's configured device type
  const activeDeviceType = (activePage?.device_type as "flagship" | "note") || getEffectiveDeviceType(boardSettings);
  
  // Device dimensions lookup
  const DEVICE_DIMS: Record<string, { rows: number; cols: number }> = {
    flagship: { rows: 6, cols: 22 },
    note: { rows: 3, cols: 15 },
  };
  const dims = DEVICE_DIMS[activeDeviceType] || DEVICE_DIMS.flagship;
  
  // Compute the display message with snoozing indicator if needed
  const displayMessage = useMemo(() => {
    const baseMessage = previewData?.message || null;
    if (!baseMessage) return null;
    
    // If silence mode is active, add the snoozing indicator
    if (silenceStatus?.active) {
      return addSnoozingIndicator(baseMessage, dims.rows, dims.cols);
    }
    
    return baseMessage;
  }, [previewData?.message, silenceStatus?.active, dims.rows, dims.cols]);

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
                  View Schedule
                </>
              ) : (
                <>
                  <ArrowLeftRight className="h-4 w-4" />
                  Change Page
                </>
              )}
            </Button>
          </div>
          
          {/* Active page name and status */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground mt-3 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-foreground">{activePageName}</span>
            </div>
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
              isLoading={isLoadingPreview || (!!activePageId && !previewData)}
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

