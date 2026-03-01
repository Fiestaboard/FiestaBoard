import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import type { ApiClient } from '@fiestaboard/shared';

// Query keys (shared naming convention with web)
export const queryKeys = {
  status: ['status'] as const,
  config: ['config'] as const,
  activePage: ['activePage'] as const,
  pages: ['pages'] as const,
  pagePreview: (pageId: string) => ['pagePreview', pageId] as const,
  boardSettings: ['boardSettings'] as const,
  plugins: ['plugins'] as const,
  plugin: (id: string) => ['plugin', id] as const,
  pluginManifest: (id: string) => ['pluginManifest', id] as const,
  schedules: ['schedules'] as const,
  scheduleEnabled: ['scheduleEnabled'] as const,
  defaultPage: ['defaultPage'] as const,
  templateVariables: ['templateVariables'] as const,
  generalConfig: ['generalConfig'] as const,
  silenceStatus: ['silenceStatus'] as const,
  version: ['version'] as const,
  updateCheck: ['updateCheck'] as const,
};

/**
 * All hooks below take an `api` parameter so they work
 * with the server URL configured at runtime (mobile) rather
 * than a static import (web).
 */

export function useStatus(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: () => api!.getStatus(),
    enabled: !!api,
    refetchInterval: 15000,
    retry: 1,
  });
}

export function useActivePage(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.activePage,
    queryFn: () => api!.getActivePage(),
    enabled: !!api,
    retry: 1,
  });
}

export function useSetActivePage(api: ApiClient | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pageId: string | null) => api!.setActivePage(pageId),
    onMutate: async (newPageId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.activePage });
      const prev = queryClient.getQueryData(queryKeys.activePage);
      queryClient.setQueryData(queryKeys.activePage, { page_id: newPageId });
      return { prev };
    },
    onError: (_err, _vars, context) => {
      if (context?.prev) {
        queryClient.setQueryData(queryKeys.activePage, context.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.activePage });
      queryClient.invalidateQueries({ queryKey: queryKeys.status });
    },
  });
}

export function usePages(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.pages,
    queryFn: () => api!.getPages(),
    enabled: !!api,
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePagePreview(api: ApiClient | null, pageId: string | null, opts?: { enabled?: boolean; refetchInterval?: number }) {
  return useQuery({
    queryKey: queryKeys.pagePreview(pageId || ''),
    queryFn: () => api!.previewPage(pageId!),
    enabled: !!api && !!pageId && (opts?.enabled !== false),
    retry: 1,
    refetchInterval: opts?.refetchInterval,
  });
}

export function useBoardSettings(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.boardSettings,
    queryFn: () => api!.getBoardSettings(),
    enabled: !!api,
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePlugins(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.plugins,
    queryFn: () => api!.listPlugins(),
    enabled: !!api,
    retry: 1,
  });
}

export function usePlugin(api: ApiClient | null, pluginId: string) {
  return useQuery({
    queryKey: queryKeys.plugin(pluginId),
    queryFn: () => api!.getPlugin(pluginId),
    enabled: !!api && !!pluginId,
    retry: 1,
  });
}

export function usePluginManifest(api: ApiClient | null, pluginId: string) {
  return useQuery({
    queryKey: queryKeys.pluginManifest(pluginId),
    queryFn: () => api!.getPluginManifest(pluginId),
    enabled: !!api && !!pluginId,
    retry: 1,
    staleTime: Infinity,
  });
}

export function useTogglePlugin(api: ApiClient | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) =>
      enabled ? api!.enablePlugin(pluginId) : api!.disablePlugin(pluginId),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.plugins });
    },
  });
}

export function useUpdatePluginConfig(api: ApiClient | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ pluginId, config }: { pluginId: string; config: Record<string, unknown> }) =>
      api!.updatePluginConfig(pluginId, config),
    onSettled: (_data, _err, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.plugin(vars.pluginId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.plugins });
    },
  });
}

export function useSchedules(api: ApiClient | null, boardId?: string) {
  return useQuery({
    queryKey: [...queryKeys.schedules, boardId],
    queryFn: () => api!.getSchedules(boardId),
    enabled: !!api,
    retry: 1,
  });
}

export function useScheduleEnabled(api: ApiClient | null, boardId?: string) {
  return useQuery({
    queryKey: [...queryKeys.scheduleEnabled, boardId],
    queryFn: () => api!.getScheduleEnabled(boardId),
    enabled: !!api,
    retry: 1,
  });
}

export function useDefaultPage(api: ApiClient | null, boardId?: string) {
  return useQuery({
    queryKey: [...queryKeys.defaultPage, boardId],
    queryFn: () => api!.getDefaultPage(boardId),
    enabled: !!api,
    retry: 1,
  });
}

export function useGeneralConfig(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.generalConfig,
    queryFn: () => api!.getGeneralConfig(),
    enabled: !!api,
    retry: 1,
  });
}

export function useSilenceStatus(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.silenceStatus,
    queryFn: () => api!.getSilenceStatus(),
    enabled: !!api,
    retry: 1,
  });
}

export function useVersion(api: ApiClient | null) {
  return useQuery({
    queryKey: queryKeys.version,
    queryFn: () => api!.getVersion(),
    enabled: !!api,
    staleTime: Infinity,
    retry: false,
  });
}

export function useToggleDevMode(api: ApiClient | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (devMode: boolean) => api!.toggleDevMode(devMode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.status });
    },
  });
}

/**
 * Derive the effective board color from board settings.
 */
export function getEffectiveBoardColor(
  boardSettings: { board_type?: 'black' | 'white' | null; boards?: Array<{ board_color?: 'black' | 'white' }> } | undefined
): 'black' | 'white' {
  const firstBoard = boardSettings?.boards?.[0];
  if (firstBoard?.board_color) return firstBoard.board_color;
  return boardSettings?.board_type ?? 'black';
}
