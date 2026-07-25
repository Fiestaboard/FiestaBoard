"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { api } from "@/lib/api";

// Query keys for cache management.
// Board-scoped keys (issue #1247): calling `activePage()` / `boardCurrentMessage()`
// without a boardId yields the legacy unscoped key, which also works as an
// invalidation prefix matching every board-scoped variant.
export const queryKeys = {
  status: ["status"] as const,
  config: ["config"] as const,
  activePage: (boardId?: string) => (boardId ? (["activePage", boardId] as const) : (["activePage"] as const)),
  boardCurrentMessage: (boardId?: string) =>
    boardId ? (["board-current-message", boardId] as const) : (["board-current-message"] as const),
  pages: ["pages"] as const,
  pagePreview: (pageId: string) => ["pagePreview", pageId] as const,
  boardSettings: ["boardSettings"] as const,
  collections: ["collections"] as const,
  schedules: (boardId: string) => ["schedules", boardId] as const,
};

// Pair with the backend's adaptive post-send refresh (max ~3s). Early tick
// catches the fast local-API case; late tick is the safety net once the
// backend's window closes. Without this, the UI would wait up to 30s for
// the next board-current-message refetch tick.
function scheduleBoardStateInvalidations(queryClient: ReturnType<typeof useQueryClient>) {
  // Unscoped key = prefix match, so every board-scoped variant refetches too.
  const key = queryKeys.boardCurrentMessage();
  setTimeout(() => queryClient.invalidateQueries({ queryKey: key }), 750);
  setTimeout(() => queryClient.invalidateQueries({ queryKey: key }), 3500);
}

// Status query - refetches every 15 seconds
export function useStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: api.getStatus,
    refetchInterval: 15000,
    retry: 1,
    staleTime: 15000,
    gcTime: 60000,
  });
}

// Config query
export function useConfig() {
  return useQuery({
    queryKey: queryKeys.config,
    queryFn: api.getConfig,
    retry: 1,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

// Active page query. Pass a boardId to read that board's active page
// (issue #1247); omitted keeps the legacy primary-board behavior.
export function useActivePage(boardId?: string) {
  return useQuery({
    queryKey: queryKeys.activePage(boardId),
    // Explicit lambda — a bare `api.getActivePage` reference would receive
    // TanStack Query's context object as the optional boardId param and
    // request board_id=[object Object] (issue #1244 regression).
    queryFn: () => api.getActivePage(boardId),
    retry: 1,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

// Board state query — what is actually on the physical board right now.
// A secondary boardId is served from the backend's per-board runtime cache
// (last-sent content); `message`/`characters` are null until something is
// sent to it (issue #1247).
export function useBoardCurrentMessage(boardId?: string) {
  return useQuery({
    queryKey: queryKeys.boardCurrentMessage(boardId),
    queryFn: () => api.getBoardCurrentMessage(boardId),
    refetchInterval: 30_000,
    staleTime: 25_000,
  });
}

// Set active page mutation - backend handles immediate send to board.
// Pass a boardId to target that board's active-page slot (issue #1247).
export function useSetActivePage(boardId?: string) {
  const queryClient = useQueryClient();
  const activePageKey = queryKeys.activePage(boardId);
  return useMutation({
    mutationFn: (pageId: string | null) => api.setActivePage(pageId, boardId),
    onMutate: async (newPageId) => {
      // Cancel any outgoing refetches to avoid overwriting optimistic update
      await queryClient.cancelQueries({ queryKey: activePageKey });

      // Snapshot the previous value
      const previousActivePage = queryClient.getQueryData(activePageKey);

      // Optimistically update to the new value
      queryClient.setQueryData(activePageKey, { page_id: newPageId });

      // Return context with the snapshotted value
      return { previousActivePage };
    },
    onError: (err, newPageId, context) => {
      // If the mutation fails, use the context returned from onMutate to roll back
      if (context?.previousActivePage) {
        queryClient.setQueryData(activePageKey, context.previousActivePage);
      }
    },
    onSuccess: () => {
      // Only invalidate status, not activePage (we already updated it optimistically)
      queryClient.invalidateQueries({ queryKey: queryKeys.status });
      scheduleBoardStateInvalidations(queryClient);
    },
    onSettled: () => {
      // Always refetch after error or success to ensure consistency
      queryClient.invalidateQueries({ queryKey: activePageKey });
    },
  });
}

// Pages list query - no auto-refetch since pages don't change frequently
export function usePages() {
  return useQuery({
    queryKey: queryKeys.pages,
    queryFn: api.getPages,
    retry: 1,
    refetchOnWindowFocus: false, // Don't refetch on window focus
    staleTime: 5 * 60 * 1000, // Consider data fresh for 5 minutes
  });
}

// Page preview query - for displaying a specific page
export function usePagePreview(pageId: string | null, options?: { enabled?: boolean; refetchInterval?: number }) {
  return useQuery({
    queryKey: queryKeys.pagePreview(pageId || ""),
    queryFn: () => (pageId ? api.previewPage(pageId) : Promise.reject("No page ID")),
    enabled: !!pageId && options?.enabled !== false,
    retry: 1,
    refetchInterval: options?.refetchInterval,
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

// Collections query
export function useCollections() {
  return useQuery({
    queryKey: queryKeys.collections,
    queryFn: api.getCollections,
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });
}

// Board settings query - for UI display preferences
export function useBoardSettings() {
  return useQuery({
    queryKey: queryKeys.boardSettings,
    queryFn: api.getBoardSettings,
    retry: 1,
    staleTime: 5 * 60 * 1000, // Consider data fresh for 5 minutes
  });
}

/**
 * Prefetch pages and board settings into the React Query cache.
 * Call on hover/focus of the "Pages" nav link so data is ready when the
 * user navigates, eliminating the loading waterfall on first visit.
 */
export function usePrefetchPagesData() {
  const queryClient = useQueryClient();
  return useCallback(() => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.pages,
      queryFn: api.getPages,
      staleTime: 5 * 60 * 1000,
    });
    queryClient.prefetchQuery({
      queryKey: queryKeys.boardSettings,
      queryFn: api.getBoardSettings,
      staleTime: 5 * 60 * 1000,
    });
  }, [queryClient]);
}

/**
 * Derive the effective board color from board settings.
 * Prefers the first board instance's board_color over the legacy board_type field.
 */
export function getEffectiveBoardColor(
  boardSettings:
    { board_type?: "black" | "white" | null; boards?: Array<{ board_color?: "black" | "white" }> } | undefined,
): "black" | "white" {
  const firstBoard = boardSettings?.boards?.[0];
  if (firstBoard?.board_color) return firstBoard.board_color;
  return boardSettings?.board_type ?? "black";
}

/**
 * Derive the effective device type from board settings.
 * Returns the first board instance's device_type, defaulting to "flagship".
 */
export function getEffectiveDeviceType(
  boardSettings: { boards?: Array<{ device_type?: string }> } | undefined,
): "flagship" | "note" {
  const firstBoard = boardSettings?.boards?.[0];
  if (firstBoard?.device_type === "note") return "note";
  return "flagship";
}
