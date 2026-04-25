/**
 * Utility functions for managing page preview cache in localStorage
 * This cache is used by PageGridSelector to show instant previews
 */

const BATCH_CACHE_KEY = "fiestaboard_previews_batch";

/**
 * Clear all preview cache from localStorage
 */
export function clearPreviewCache(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(BATCH_CACHE_KEY);
  }
}

/**
 * Clear preview cache for a specific page
 */
export function clearPreviewCacheForPage(pageId: string): void {
  if (typeof window === "undefined") return;
  const cached = localStorage.getItem(BATCH_CACHE_KEY);
  if (!cached) return;
  try {
    const previews = JSON.parse(cached);
    delete previews[pageId];
    localStorage.setItem(BATCH_CACHE_KEY, JSON.stringify(previews));
  } catch {
    // If parsing fails, clear entire cache
    localStorage.removeItem(BATCH_CACHE_KEY);
  }
}
