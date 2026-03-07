"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { api } from "@/lib/api";
import { MonitorDashboard } from "@/components/debug/monitor-dashboard";
import { Card, CardContent } from "@/components/ui/card";
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
          <h1 className="page-title flex items-center gap-3">
            <Activity className="h-7 w-7" />
            System Monitor
          </h1>
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
                This provides Grafana-like monitoring for CPU, memory, disk, network,
                process status, request metrics, error tracking, and logs.
              </p>
            </CardContent>
          </Card>
        )}

        {isEnabled && <MonitorDashboard />}
      </div>
    </div>
  );
}
