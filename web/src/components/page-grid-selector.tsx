"use client";

import { useEffect, useCallback, useMemo, useState, memo } from "react";
import { usePages, useBoardSettings, getEffectiveBoardColor } from "@/hooks/use-board";
import { Skeleton } from "@/components/ui/skeleton";
import { LayoutTemplate, Loader2, Clock } from "lucide-react";
import { BoardDisplay } from "@/components/board-display";
import type { Page, PagePreviewResponse, PagePreviewBatchResponse } from "@/lib/api";
import { api } from "@/lib/api";

// Cache key for batch previews in localStorage
const BATCH_CACHE_KEY = "fiestaboard_previews_batch";

// Type for cached preview data
interface CachedPreviewData {
  preview: PagePreviewResponse;
  pageUpdatedAt: string;
  cachedAt: string;
}

// Get all cached previews from localStorage
function getCachedPreviews(): Record<string, CachedPreviewData> {
  if (typeof window === "undefined") return {};
  
  try {
    const cached = localStorage.getItem(BATCH_CACHE_KEY);
    if (!cached) return {};
    return JSON.parse(cached);
  } catch (error) {
    console.error("Error reading preview cache:", error);
    return {};
  }
}

// Save all previews to localStorage
function setCachedPreviews(previews: Record<string, CachedPreviewData>): void {
  if (typeof window === "undefined") return;
  
  try {
    localStorage.setItem(BATCH_CACHE_KEY, JSON.stringify(previews));
  } catch (error) {
    console.error("Error writing preview cache:", error);
  }
}

// Get a single cached preview for a page
function getCachedPreview(pageId: string, pageUpdatedAt: string): PagePreviewResponse | null {
  const allPreviews = getCachedPreviews();
  const cached = allPreviews[pageId];
  
  if (!cached || cached.pageUpdatedAt !== pageUpdatedAt) {
    return null;
  }
  
  return cached.preview;
}

// Save a single preview to localStorage
function setCachedPreview(pageId: string, pageUpdatedAt: string, preview: PagePreviewResponse): void {
  const allPreviews = getCachedPreviews();
  allPreviews[pageId] = {
    preview,
    pageUpdatedAt,
    cachedAt: new Date().toISOString(),
  };
  setCachedPreviews(allPreviews);
}

// Check if a cached preview is still valid for a page
function isCacheValid(cached: CachedPreviewData | undefined, pageUpdatedAt: string): boolean {
  if (!cached) return false;
  return cached.pageUpdatedAt === pageUpdatedAt;
}

// Mini preview component for each page button - receives preview data from parent
// Memoized to prevent unnecessary re-renders when parent updates
const PageButtonPreview = memo(function PageButtonPreview({ 
  preview,
  isLoading,
  boardType = "black",
  deviceType = "flagship"
}: { 
  preview: PagePreviewResponse | null;
  isLoading: boolean;
  boardType?: "black" | "white" | null;
  deviceType?: "flagship" | "note";
}) {
  // Show simple spinner when loading instead of BoardDisplay loading animation
  // This prevents lag when all displays try to load at once
  if (isLoading && !preview) {
    return (
      <div className="w-full flex items-center justify-center py-4" role="status">
        <Loader2 className="h-4 w-4 text-muted-foreground animate-spin" aria-hidden="true" />
        <span className="sr-only">Loading preview</span>
      </div>
    );
  }

  return (
    <div 
      className="w-full hover-stable overflow-hidden -mr-3"
      style={{
        maskImage: 'linear-gradient(to right, black 60%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(to right, black 60%, transparent 100%)'
      }}
    >
      <BoardDisplay 
        message={preview?.message || null} 
        isLoading={false}
        size="sm"
        boardType={boardType ?? "black"}
        deviceType={deviceType}
      />
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison: only re-render if preview, loading state, or deviceType changes
  return prevProps.preview === nextProps.preview && 
         prevProps.isLoading === nextProps.isLoading &&
         prevProps.boardType === nextProps.boardType &&
         prevProps.deviceType === nextProps.deviceType;
});

// Memoized page button component to prevent unnecessary re-renders
const PageButton = memo(function PageButton({
  page,
  preview,
  isLoadingPreview,
  isActive,
  isPending,
  onSelect,
  showActiveIndicator = true,
  boardType = "black",
}: {
  page: Page;
  preview: PagePreviewResponse | null;
  isLoadingPreview: boolean;
  isActive: boolean;
  isPending: boolean;
  onSelect: (pageId: string) => void;
  showActiveIndicator?: boolean;
  boardType?: "black" | "white" | null;
}) {
  const TypeIcon = LayoutTemplate;
  
  // Pre-compute className to avoid template string parsing on every render
  // Remove ALL transitions for instant, snappy feedback
  const buttonClassName = isActive
    ? "group relative flex flex-col gap-2 p-3 rounded-lg border-2 border-primary bg-primary/10 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed text-left page-button-container"
    : "group relative flex flex-col gap-2 p-3 rounded-lg border-2 border-border hover:border-primary/50 hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed text-left page-button-container";
  
  // No transitions - instant color changes
  const iconClassName = isActive
    ? "h-4 w-4 shrink-0 text-primary"
    : "h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground";
  
  const nameClassName = isActive
    ? "text-sm font-medium truncate text-foreground"
    : "text-sm font-medium truncate text-muted-foreground group-hover:text-foreground";
  
  // Memoize click handler to prevent function recreation
  const handleClick = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (!isPending) {
      onSelect(page.id);
    }
  }, [page.id, isPending, onSelect]);
  
  return (
    <button
      key={page.id}
      onClick={handleClick}
      disabled={isPending}
      className={buttonClassName}
      type="button"
      aria-pressed={isActive}
    >
      {/* Page info header */}
      <div className="flex items-center gap-2 min-w-0">
        <TypeIcon className={iconClassName} />
        <span className={nameClassName}>
          {page.name}
        </span>
      </div>
      
      {/* Mini preview - isolated to prevent hover re-renders */}
      <div className="hover-stable">
        <PageButtonPreview 
          preview={preview} 
          isLoading={isLoadingPreview}
          boardType={boardType}
          deviceType={(page.device_type as "flagship" | "note") || "flagship"}
        />
      </div>
      
      {/* Active indicator */}
      {showActiveIndicator && isActive && (
        <div className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-12 h-0.5 bg-primary rounded-full" />
      )}
    </button>
  );
}, (prevProps, nextProps) => {
  // Only re-render if relevant props change
  return prevProps.page.id === nextProps.page.id &&
         prevProps.preview === nextProps.preview &&
         prevProps.isLoadingPreview === nextProps.isLoadingPreview &&
         prevProps.isActive === nextProps.isActive &&
         prevProps.isPending === nextProps.isPending &&
         prevProps.page.updated_at === nextProps.page.updated_at &&
         prevProps.showActiveIndicator === nextProps.showActiveIndicator &&
         prevProps.boardType === nextProps.boardType;
});

// Lightweight list item for list view mode - no BoardDisplay preview
const PageListItem = memo(function PageListItem({
  page,
  isActive,
  isPending,
  onSelect,
}: {
  page: Page;
  isActive: boolean;
  isPending: boolean;
  onSelect: (pageId: string) => void;
}) {
  const handleClick = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (!isPending) {
      onSelect(page.id);
    }
  }, [page.id, isPending, onSelect]);

  const formattedDate = useMemo(() => {
    if (!page.updated_at) return null;
    try {
      return new Date(page.updated_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return null;
    }
  }, [page.updated_at]);

  const buttonClassName = isActive
    ? "group flex items-center gap-3 w-full p-3 rounded-lg border-2 border-primary bg-primary/10 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed text-left"
    : "group flex items-center gap-3 w-full p-3 rounded-lg border-2 border-border hover:border-primary/50 hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed text-left";

  const iconClassName = isActive
    ? "h-4 w-4 shrink-0 text-primary"
    : "h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground";

  const nameClassName = isActive
    ? "text-sm font-medium truncate text-foreground"
    : "text-sm font-medium truncate text-muted-foreground group-hover:text-foreground";

  return (
    <button
      onClick={handleClick}
      disabled={isPending}
      className={buttonClassName}
      type="button"
      aria-pressed={isActive}
    >
      <LayoutTemplate className={iconClassName} />
      <span className={nameClassName}>{page.name}</span>
      {formattedDate && (
        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground shrink-0">
          <Clock className="h-3 w-3" />
          {formattedDate}
        </span>
      )}
    </button>
  );
}, (prevProps, nextProps) => {
  return prevProps.page.id === nextProps.page.id &&
         prevProps.isActive === nextProps.isActive &&
         prevProps.isPending === nextProps.isPending &&
         prevProps.page.updated_at === nextProps.page.updated_at;
});

export type ViewMode = "grid" | "list";

export interface PageGridSelectorProps {
  /** The currently active/selected page ID (for highlighting) */
  activePageId?: string | null;
  /** Callback when a page is selected */
  onSelectPage: (pageId: string) => void;
  /** Whether a selection is pending (for loading states) */
  isPending?: boolean;
  /** Whether to show the active indicator line */
  showActiveIndicator?: boolean;
  /** Label text above the grid */
  label?: string;
  /** Filter pages by device type */
  deviceTypeFilter?: "flagship" | "note";
  /** View mode: "grid" shows previews, "list" shows compact list */
  viewMode?: ViewMode;
}

export function PageGridSelector({
  activePageId = null,
  onSelectPage,
  isPending = false,
  showActiveIndicator = true,
  label = "SELECT PAGE",
  deviceTypeFilter,
  viewMode = "grid",
}: PageGridSelectorProps) {
  // Fetch all pages
  const { data: pagesData, isLoading: isLoadingPages } = usePages();
  
  // Fetch board settings for display type
  const { data: boardSettings } = useBoardSettings();
  
  // Memoize pages array to prevent unnecessary re-renders, with optional device type filter
  const pages = useMemo(() => {
    const allPages = pagesData?.pages || [];
    if (!deviceTypeFilter) return allPages;
    return allPages.filter(p => (p.device_type || "flagship") === deviceTypeFilter);
  }, [pagesData, deviceTypeFilter]);
  
  // State for batch preview data
  const [previews, setPreviews] = useState<Record<string, PagePreviewResponse>>({});
  const [loadingPreviews, setLoadingPreviews] = useState(true);
  
  // Fetch batch previews when pages change (only in grid mode)
  useEffect(() => {
    if (viewMode === "list" || pages.length === 0) {
      setLoadingPreviews(false);
      return;
    }
    
    // Check cache first for instant render
    const cachedPreviews = getCachedPreviews();
    const initialPreviews: Record<string, PagePreviewResponse> = {};
    const pagesToFetch: string[] = [];
    
    for (const page of pages) {
      const cached = cachedPreviews[page.id];
      const pageUpdatedAt = page.updated_at || "";
      
      if (isCacheValid(cached, pageUpdatedAt)) {
        initialPreviews[page.id] = cached.preview;
      } else {
        pagesToFetch.push(page.id);
      }
    }
    
    // Set cached previews immediately for instant render
    if (Object.keys(initialPreviews).length > 0) {
      setPreviews(initialPreviews);
      setLoadingPreviews(pagesToFetch.length > 0);
    }
    
    // Fetch missing previews in batch
    if (pagesToFetch.length > 0) {
      let mounted = true;
      
      const fetchBatchPreviews = async () => {
        try {
          const result = await api.previewPagesBatch(pagesToFetch);
          
          if (mounted && result.previews) {
            // Update cache with new previews
            const newCachedPreviews = { ...cachedPreviews };
            
            for (const [pageId, preview] of Object.entries(result.previews)) {
              if (preview.available) {
                const page = pages.find(p => p.id === pageId);
                if (page) {
                  newCachedPreviews[pageId] = {
                    preview,
                    pageUpdatedAt: page.updated_at || "",
                    cachedAt: new Date().toISOString(),
                  };
                }
              }
            }
            
            setCachedPreviews(newCachedPreviews);
            
            // Merge with existing cached previews
            setPreviews(prev => ({
              ...prev,
              ...result.previews
            }));
            setLoadingPreviews(false);
          }
        } catch (error) {
          console.error("Failed to fetch batch previews:", error);
          if (mounted) {
            setLoadingPreviews(false);
          }
        }
      };
      
      fetchBatchPreviews();
      
      return () => {
        mounted = false;
      };
    } else {
      setLoadingPreviews(false);
    }
  }, [pages, viewMode]);
  
  if (isLoadingPages) {
    return (
      <div aria-busy="true">
        {label && (
          <span className="text-xs font-medium text-muted-foreground mb-3 block">
            {label}
          </span>
        )}
        {viewMode === "list" ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        )}
      </div>
    );
  }
  
  if (pages.length === 0) {
    return (
      <div className="text-center text-sm text-muted-foreground py-4">
        <p>No pages created yet.</p>
        <p className="mt-1">
          <a href={`/pages/new${deviceTypeFilter ? `?device=${deviceTypeFilter}` : ''}`} className="text-primary hover:underline">
            Create your first page
          </a>
        </p>
      </div>
    );
  }
  
  return (
    <div>
      {label && (
        <span className="text-xs font-medium text-muted-foreground mb-3 block">
          {label}
        </span>
      )}
      {viewMode === "list" ? (
        <div className="flex flex-col gap-2" role="group" aria-label={label || "Page selection"}>
          {pages.map((page) => (
            <PageListItem
              key={page.id}
              page={page}
              isActive={page.id === activePageId}
              isPending={isPending}
              onSelect={onSelectPage}
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="group" aria-label={label || "Page selection"}>
          {pages.map((page) => (
            <PageButton
              key={page.id}
              page={page}
              preview={previews[page.id] || null}
              isLoadingPreview={loadingPreviews}
              isActive={page.id === activePageId}
              isPending={isPending}
              onSelect={onSelectPage}
              showActiveIndicator={showActiveIndicator}
              boardType={getEffectiveBoardColor(boardSettings)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

