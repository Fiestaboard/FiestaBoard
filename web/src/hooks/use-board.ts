"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api } from "@/lib/api";

// Query keys for cache management
export const queryKeys = {
  status: ["status"] as const,
  config: ["config"] as const,
  activePage: ["activePage"] as const,
  pages: ["pages"] as const,
  pagePreview: (pageId: string) => ["pagePreview", pageId] as const,
  boardSettings: ["boardSettings"] as const,
  carousels: ["carousels"] as const,
  schedules: (boardId: string) => ["schedules", boardId] as const,
};

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

// Active page query
export function useActivePage() {
  return useQuery({
    queryKey: queryKeys.activePage,
    queryFn: api.getActivePage,
    retry: 1,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

// Set active page mutation - backend handles immediate send to board
export function useSetActivePage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pageId: string | null) => api.setActivePage(pageId),
    onMutate: async (newPageId) => {
      // Cancel any outgoing refetches to avoid overwriting optimistic update
      await queryClient.cancelQueries({ queryKey: queryKeys.activePage });
      
      // Snapshot the previous value
      const previousActivePage = queryClient.getQueryData(queryKeys.activePage);
      
      // Optimistically update to the new value
      queryClient.setQueryData(queryKeys.activePage, { page_id: newPageId });
      
      // Return context with the snapshotted value
      return { previousActivePage };
    },
    onError: (err, newPageId, context) => {
      // If the mutation fails, use the context returned from onMutate to roll back
      if (context?.previousActivePage) {
        queryClient.setQueryData(queryKeys.activePage, context.previousActivePage);
      }
    },
    onSuccess: () => {
      // Only invalidate status, not activePage (we already updated it optimistically)
      queryClient.invalidateQueries({ queryKey: queryKeys.status });
    },
    onSettled: () => {
      // Always refetch after error or success to ensure consistency
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage });
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
    enabled: !!pageId && (options?.enabled !== false),
    retry: 1,
    refetchInterval: options?.refetchInterval,
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

// Carousels query
export function useCarousels() {
  return useQuery({
    queryKey: queryKeys.carousels,
    queryFn: api.getCarousels,
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
  boardSettings: { board_type?: "black" | "white" | null; boards?: Array<{ board_color?: "black" | "white" }> } | undefined
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
  boardSettings: { boards?: Array<{ device_type?: string }> } | undefined
): "flagship" | "note" {
  const firstBoard = boardSettings?.boards?.[0];
  if (firstBoard?.device_type === "note") return "note";
  return "flagship";
}

