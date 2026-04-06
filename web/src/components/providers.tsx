"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { SidebarProvider } from "@/components/sidebar-context";
import { FormatPreferencesProvider } from "@/hooks/use-format-preferences";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 1000 * 60, // 1 minute
            refetchOnWindowFocus: false,
            refetchOnMount: true, // Refetch on mount to ensure invalidated queries update (critical for cache busting)
            gcTime: 1000 * 60 * 5, // Keep unused data in cache for 5 minutes
            retry: 2, // Retry failed requests twice
            retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000), // Exponential backoff: 1s, 2s, max 30s
            networkMode: 'online', // Only retry when online
          },
          mutations: {
            retry: 1, // Retry mutations once on failure
            networkMode: 'online',
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
      >
        <SidebarProvider>
          <ConfigOverridesProvider>
            <FormatPreferencesProvider>{children}</FormatPreferencesProvider>
          </ConfigOverridesProvider>
        </SidebarProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

