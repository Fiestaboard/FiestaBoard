"use client";

import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, RefreshCw, ExternalLink, AlertTriangle, Globe, List } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { api, RequestLogEntry, ClientErrorEntry } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";

type EventItem =
  | { kind: "request"; time: string; entry: RequestLogEntry }
  | { kind: "client_error"; time: string; entry: ClientErrorEntry };

function EventsList({ events }: { events: EventItem[] }) {
  if (events.length === 0)
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        No events yet. Traffic and client errors will appear here.
      </p>
    );

  return (
    <ScrollArea className="h-[280px] w-full rounded-md border border-border/50">
      <div className="p-2 space-y-0.5">
        {events.map((ev, i) => {
          if (ev.kind === "request") {
            const e = ev.entry;
            const isError = e.status >= 400;
            return (
              <div
                key={`req-${i}-${e.timestamp}`}
                className={`flex items-center gap-2 py-1.5 px-2 rounded text-xs font-mono ${
                  isError ? "bg-destructive/10" : "hover:bg-muted/60"
                }`}
              >
                <span className="text-muted-foreground shrink-0 w-16">{new Date(e.timestamp).toLocaleTimeString()}</span>
                <Badge variant="outline" className="shrink-0 text-[10px] px-1">REQ</Badge>
                <span className="shrink-0 w-10">{e.method}</span>
                <span className="truncate min-w-0" title={e.path}>{e.path}</span>
                <StatusBadge status={e.status} />
                <span className="text-muted-foreground shrink-0 ml-auto">{e.duration_ms.toFixed(0)}ms</span>
              </div>
            );
          }
          const e = ev.entry;
          return (
            <div
              key={`err-${i}-${e.timestamp}`}
              className="flex items-center gap-2 py-1.5 px-2 rounded text-xs font-mono bg-destructive/10"
            >
              <span className="text-muted-foreground shrink-0 w-16">{new Date(e.timestamp).toLocaleTimeString()}</span>
              <Badge variant="destructive" className="shrink-0 text-[10px] px-1">ERR</Badge>
              <span className="shrink-0 w-10">{e.method}</span>
              <span className="truncate min-w-0" title={e.path}>{e.path}</span>
              <span className="text-destructive truncate max-w-[180px]" title={e.error_message}>{e.error_message}</span>
            </div>
          );
        })}
      </div>
    </ScrollArea>
  );
}

function StatusBadge({ status }: { status: number }) {
  if (status >= 500)
    return <Badge variant="destructive">{status}</Badge>;
  if (status >= 400)
    return <Badge className="bg-yellow-600 text-white hover:bg-yellow-700">{status}</Badge>;
  return <Badge variant="secondary">{status}</Badge>;
}

function RequestLogTable({ entries }: { entries: RequestLogEntry[] }) {
  if (entries.length === 0)
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No requests logged yet. Make some API calls and they will appear here.
      </p>
    );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2 px-2 font-medium text-muted-foreground">Time</th>
            <th className="py-2 px-2 font-medium text-muted-foreground">Method</th>
            <th className="py-2 px-2 font-medium text-muted-foreground">Path</th>
            <th className="py-2 px-2 font-medium text-muted-foreground">Status</th>
            <th className="py-2 px-2 font-medium text-muted-foreground text-right">Duration</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-muted/50">
              <td className="py-1.5 px-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                {new Date(entry.timestamp).toLocaleTimeString()}
              </td>
              <td className="py-1.5 px-2 font-mono text-xs">{entry.method}</td>
              <td className="py-1.5 px-2 font-mono text-xs max-w-[300px] truncate" title={entry.path}>
                {entry.path}
              </td>
              <td className="py-1.5 px-2">
                <StatusBadge status={entry.status} />
              </td>
              <td className="py-1.5 px-2 font-mono text-xs text-right">
                {entry.duration_ms.toFixed(1)}ms
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClientErrorTable({ entries }: { entries: ClientErrorEntry[] }) {
  if (entries.length === 0)
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No client errors reported. Errors from failed API calls in the browser will appear here.
      </p>
    );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2 px-2 font-medium text-muted-foreground">Time</th>
            <th className="py-2 px-2 font-medium text-muted-foreground">Method</th>
            <th className="py-2 px-2 font-medium text-muted-foreground">Path</th>
            <th className="py-2 px-2 font-medium text-muted-foreground">Status</th>
            <th className="py-2 px-2 font-medium text-muted-foreground">Error</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-muted/50">
              <td className="py-1.5 px-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                {new Date(entry.timestamp).toLocaleTimeString()}
              </td>
              <td className="py-1.5 px-2 font-mono text-xs">{entry.method}</td>
              <td className="py-1.5 px-2 font-mono text-xs max-w-[200px] truncate" title={entry.path}>
                {entry.path}
              </td>
              <td className="py-1.5 px-2">
                {entry.status ? <StatusBadge status={entry.status} /> : <span className="text-xs text-muted-foreground">N/A</span>}
              </td>
              <td className="py-1.5 px-2 text-xs text-destructive max-w-[300px] truncate" title={entry.error_message}>
                {entry.error_message}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DebugMonitorPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const enabledQuery = useQuery({
    queryKey: ["debug-monitor", "enabled"],
    queryFn: api.getDebugMonitorEnabled,
    retry: 1,
    staleTime: 30_000,
  });

  const isEnabled = enabledQuery.data?.enabled;

  const requestLogQuery = useQuery({
    queryKey: ["debug-request-log", statusFilter],
    queryFn: () =>
      api.getRequestLog({
        limit: 100,
        status: statusFilter !== "all" ? statusFilter : undefined,
      }),
    enabled: !!isEnabled,
    refetchInterval: 5_000,
  });

  const clientErrorsQuery = useQuery({
    queryKey: ["debug-client-errors"],
    queryFn: () => api.getClientErrors({ limit: 50 }),
    enabled: !!isEnabled,
    refetchInterval: 5_000,
  });

  const grafanaUrl = "/grafana/";

  const handleRefresh = useCallback(() => {
    requestLogQuery.refetch();
    clientErrorsQuery.refetch();
  }, [requestLogQuery, clientErrorsQuery]);

  const errorCount = requestLogQuery.data?.entries.filter(
    (e) => e.status >= 400
  ).length ?? 0;

  const eventsList = useMemo((): EventItem[] => {
    const requests: EventItem[] = (requestLogQuery.data?.entries ?? []).map((entry) => ({
      kind: "request" as const,
      time: entry.timestamp,
      entry,
    }));
    const errors: EventItem[] = (clientErrorsQuery.data?.entries ?? []).map((entry) => ({
      kind: "client_error" as const,
      time: entry.timestamp,
      entry,
    }));
    const combined = [...requests, ...errors].sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());
    return combined.slice(0, 80);
  }, [requestLogQuery.data?.entries, clientErrorsQuery.data?.entries]);

  return (
    <PageLayout>
        <div className="animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <div className="flex items-center justify-between mb-4">
            <h1 className="page-title flex items-center gap-3">
              <Activity className="h-7 w-7" />
              System Monitor
            </h1>
            {isEnabled && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRefresh}
                  disabled={requestLogQuery.isFetching}
                >
                  <RefreshCw className={`h-4 w-4 mr-1.5 ${requestLogQuery.isFetching ? "animate-spin" : ""}`} />
                  Refresh
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <a href={grafanaUrl} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-1.5" />
                    Open Grafana
                  </a>
                </Button>
              </div>
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
              <Activity className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h2 className="text-lg font-semibold mb-2">Monitoring is Disabled</h2>
              <p className="text-sm text-muted-foreground max-w-lg mx-auto">
                To enable monitoring, set{" "}
                <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-xs">LOCAL_MONITORING=true</code>{" "}
                in your <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-xs">.env</code> file and restart the container.
              </p>
              <p className="text-xs text-muted-foreground mt-4">
                Prometheus and Grafana run inside the same container.
                Monitoring is enabled by default in development.
              </p>
            </CardContent>
          </Card>
        )}

        {isEnabled && (
          <div className="space-y-4 animate-card-fade-in" style={{ animationDelay: "100ms" }}>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Card>
                <CardContent className="py-3 text-center">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Logged Requests</p>
                  <p className="text-2xl font-bold mt-1">
                    {requestLogQuery.data?.total ?? "—"}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="py-3 text-center">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Errors in View</p>
                  <p className={`text-2xl font-bold mt-1 ${errorCount > 0 ? "text-destructive" : ""}`}>
                    {errorCount}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="py-3 text-center">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Client Errors</p>
                  <p className={`text-2xl font-bold mt-1 ${(clientErrorsQuery.data?.total ?? 0) > 0 ? "text-destructive" : ""}`}>
                    {clientErrorsQuery.data?.total ?? "—"}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="py-3 text-center">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Grafana</p>
                  <a
                    href={grafanaUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary underline-offset-4 hover:underline inline-flex items-center gap-1 mt-1"
                  >
                    <Globe className="h-3.5 w-3.5" />
                    Dashboards
                  </a>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardContent className="pt-4 pb-3 px-4">
                <h2 className="text-sm font-semibold flex items-center gap-2 mb-2">
                  <List className="h-4 w-4 text-muted-foreground" />
                  Recent events
                </h2>
                <p className="text-xs text-muted-foreground mb-3">
                  Running list of API requests and client errors (newest first). Auto-refreshes every 5s.
                </p>
                {requestLogQuery.isLoading && clientErrorsQuery.isLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 6 }).map((_, i) => (
                      <Skeleton key={i} className="h-6 w-full" />
                    ))}
                  </div>
                ) : (
                  <EventsList events={eventsList} />
                )}
              </CardContent>
            </Card>

            <Tabs defaultValue="request-log">
              <div className="flex items-center justify-between">
                <TabsList>
                  <TabsTrigger value="request-log" className="gap-1.5">
                    <Activity className="h-3.5 w-3.5" />
                    Request Log
                  </TabsTrigger>
                  <TabsTrigger value="client-errors" className="gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Client Errors
                    {(clientErrorsQuery.data?.total ?? 0) > 0 && (
                      <Badge variant="destructive" className="ml-1 h-5 min-w-[20px] px-1">
                        {clientErrorsQuery.data?.total}
                      </Badge>
                    )}
                  </TabsTrigger>
                </TabsList>
                <div className="flex items-center gap-2">
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger className="w-[140px] h-8 text-xs">
                      <SelectValue placeholder="Filter status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All statuses</SelectItem>
                      <SelectItem value="2xx">2xx Success</SelectItem>
                      <SelectItem value="4xx">4xx Client</SelectItem>
                      <SelectItem value="5xx">5xx Server</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <TabsContent value="request-log" className="mt-3">
                <Card>
                  <CardContent className="py-3 px-0">
                    {requestLogQuery.isLoading ? (
                      <div className="space-y-2 px-4">
                        {Array.from({ length: 5 }).map((_, i) => (
                          <Skeleton key={i} className="h-6 w-full" />
                        ))}
                      </div>
                    ) : requestLogQuery.isError ? (
                      <p className="text-sm text-destructive text-center py-4">
                        Failed to load request log: {(requestLogQuery.error as Error)?.message}
                      </p>
                    ) : (
                      <RequestLogTable entries={requestLogQuery.data?.entries ?? []} />
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="client-errors" className="mt-3">
                <Card>
                  <CardContent className="py-3 px-0">
                    {clientErrorsQuery.isLoading ? (
                      <div className="space-y-2 px-4">
                        {Array.from({ length: 3 }).map((_, i) => (
                          <Skeleton key={i} className="h-6 w-full" />
                        ))}
                      </div>
                    ) : clientErrorsQuery.isError ? (
                      <p className="text-sm text-destructive text-center py-4">
                        Failed to load client errors: {(clientErrorsQuery.error as Error)?.message}
                      </p>
                    ) : (
                      <ClientErrorTable entries={clientErrorsQuery.data?.entries ?? []} />
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        )}
    </PageLayout>
  );
}
