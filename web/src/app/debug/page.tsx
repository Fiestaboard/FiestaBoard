"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export default function DebugMonitorPage() {
  const enabledQuery = useQuery({
    queryKey: ["debug-monitor", "enabled"],
    queryFn: api.getDebugMonitorEnabled,
    retry: 1,
    staleTime: 30_000,
  });

  const isEnabled = enabledQuery.data?.enabled;

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 max-w-full">
        <div className="animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <div className="flex items-center justify-between mb-4">
            <h1 className="page-title flex items-center gap-3 mb-0">
              <Activity className="h-7 w-7" />
              System Monitor
            </h1>
            {isEnabled && (
              <Button variant="outline" size="sm" asChild>
                <a href="/glances/" target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                  Open in New Tab
                </a>
              </Button>
            )}
          </div>
        </div>

        {enabledQuery.isLoading && (
          <Card>
            <CardContent className="py-12">
              <div className="flex flex-col items-center gap-3">
                <Skeleton className="h-6 w-48" />
                <Skeleton className="h-4 w-64" />
              </div>
            </CardContent>
          </Card>
        )}

        {enabledQuery.isError && (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-destructive font-medium">
                Failed to check debug mode status
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                {(enabledQuery.error as Error)?.message}
              </p>
            </CardContent>
          </Card>
        )}

        {enabledQuery.data && !isEnabled && (
          <Card>
            <CardContent className="py-12 text-center">
              <Activity className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
              <h2 className="text-lg font-semibold mb-2">Debug Monitor is Disabled</h2>
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                To enable the system monitoring dashboard, set the{" "}
                <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-xs">DEBUG_MODE=true</code>{" "}
                environment variable and restart the container.
              </p>
              <p className="text-xs text-muted-foreground mt-3">
                This enables Glances, an open-source system monitoring tool that provides
                real-time CPU, memory, disk, network, and process monitoring.
              </p>
            </CardContent>
          </Card>
        )}

        {isEnabled && (
          <div className="animate-card-fade-in" style={{ animationDelay: "100ms" }}>
            <div className="rounded-xl border bg-card shadow-card overflow-hidden" style={{ height: "calc(100vh - 140px)", minHeight: "500px" }}>
              <iframe
                src="/glances/"
                title="Glances System Monitor"
                className="w-full h-full border-0"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
