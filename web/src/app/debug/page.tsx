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

  // Grafana runs on port 3030 on the same host
  const grafanaUrl =
    typeof window !== "undefined"
      ? `${window.location.protocol}//${window.location.hostname}:3030`
      : "http://localhost:3030";

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
                <a href={grafanaUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                  Open Grafana
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
                Failed to check monitoring status
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
              <h2 className="text-lg font-semibold mb-2">Monitoring is Disabled</h2>
              <p className="text-sm text-muted-foreground max-w-lg mx-auto">
                To enable Grafana monitoring, set{" "}
                <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-xs">LOCAL_MONITORING=true</code>{" "}
                and start the monitoring stack:
              </p>
              <pre className="mt-3 px-4 py-2 rounded bg-muted font-mono text-xs text-left inline-block max-w-lg">
                docker compose -f docker-compose.yml \{"\n"}  -f docker-compose.monitoring.yml up -d
              </pre>
              <p className="text-xs text-muted-foreground mt-4">
                Monitoring is enabled by default in development. For production,
                add the monitoring compose overlay and set <code className="px-1 py-0.5 rounded bg-muted font-mono text-xs">LOCAL_MONITORING=true</code>.
              </p>
            </CardContent>
          </Card>
        )}

        {isEnabled && (
          <div className="animate-card-fade-in" style={{ animationDelay: "100ms" }}>
            {/* Height accounts for page header (~60px) + container padding (~80px) */}
            <div className="rounded-xl border bg-card shadow-card overflow-hidden" style={{ height: "calc(100vh - 140px)", minHeight: "500px" }}>
              <iframe
                src={`${grafanaUrl}/d/fiestaboard-system/fiestaboard-system?orgId=1&kiosk`}
                title="Grafana System Monitor"
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
