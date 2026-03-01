import { useEffect, useState, createContext, useContext } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClientProvider } from '@tanstack/react-query';
import { AppState, type AppStateStatus } from 'react-native';
import { focusManager } from '@tanstack/react-query';
import { createQueryClient } from '../lib/query-client';
import { useServer } from '../hooks/use-server';
import type { ApiClient } from '@fiestaboard/shared';

// Context to provide the API client throughout the app
export const ServerContext = createContext<{
  serverUrl: string | null;
  api: ApiClient | null;
  connected: boolean;
  loading: boolean;
  setServer: (url: string) => Promise<void>;
  disconnect: () => Promise<void>;
  testConnection: (url: string) => Promise<boolean>;
}>({
  serverUrl: null,
  api: null,
  connected: false,
  loading: true,
  setServer: async () => {},
  disconnect: async () => {},
  testConnection: async () => false,
});

export function useServerContext() {
  return useContext(ServerContext);
}

const queryClient = createQueryClient();

export default function RootLayout() {
  const server = useServer();

  // Auto-refetch when app comes to foreground
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (status: AppStateStatus) => {
      focusManager.setFocused(status === 'active');
    });
    return () => subscription.remove();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ServerContext.Provider value={server}>
        <StatusBar style="auto" />
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen
            name="connect"
            options={{
              presentation: 'fullScreenModal',
              headerShown: true,
              headerTitle: 'Connect to Server',
            }}
          />
          <Stack.Screen
            name="pages/[id]"
            options={{
              headerShown: true,
              headerTitle: 'Page Detail',
              headerBackTitle: 'Back',
            }}
          />
          <Stack.Screen
            name="plugins/[id]"
            options={{
              headerShown: true,
              headerTitle: 'Plugin Settings',
              headerBackTitle: 'Back',
            }}
          />
        </Stack>
      </ServerContext.Provider>
    </QueryClientProvider>
  );
}
