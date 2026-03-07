"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Cpu,
  MemoryStick,
  HardDrive,
  Network,
  Activity,
  AlertTriangle,
  ScrollText,
  RefreshCw,
  Cog,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  type DebugMonitorSystemResponse,
  type DebugMonitorProcessesResponse,
  type DebugMonitorMetricsResponse,
  type DebugMonitorErrorsResponse,
  type DebugMonitorLogsResponse,
} from "@/lib/api";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  parts.push(`${m}m`);
  return parts.join(" ");
}

function UsageBar({ percent, color }: { percent: number; color: string }) {
  return (
    <div className="w-full h-2.5 bg-muted rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.min(percent, 100)}%` }}
      />
    </div>
  );
}

function MetricCard({
  icon: Icon,
  title,
  value,
  subtitle,
  percent,
  color,
}: {
  icon: React.ElementType;
  title: string;
  value: string;
  subtitle?: string;
  percent?: number;
  color: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-3 mb-3">
          <div className={`p-2 rounded-lg ${color}`}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-xl font-bold tracking-tight">{value}</p>
          </div>
        </div>
        {percent !== undefined && (
          <UsageBar
            percent={percent}
            color={
              percent > 90
                ? "bg-destructive"
                : percent > 70
                  ? "bg-yellow-500"
                  : "bg-emerald-500"
            }
          />
        )}
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-1.5">{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
}

// ─── System Metrics Section ──────────────────────────────────────────────────

function SystemMetrics({ data }: { data: DebugMonitorSystemResponse }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        icon={Cpu}
        title="CPU Usage"
        value={`${data.cpu.percent}%`}
        subtitle={`${data.cpu.count} cores${data.cpu.freq_mhz ? ` @ ${data.cpu.freq_mhz} MHz` : ""}${data.cpu.load_avg ? ` · Load: ${data.cpu.load_avg.map((v) => v.toFixed(2)).join(", ")}` : ""}`}
        percent={data.cpu.percent}
        color="bg-blue-500/10 text-blue-500"
      />
      <MetricCard
        icon={MemoryStick}
        title="Memory"
        value={`${data.memory.percent}%`}
        subtitle={`${formatBytes(data.memory.used_bytes)} / ${formatBytes(data.memory.total_bytes)}`}
        percent={data.memory.percent}
        color="bg-purple-500/10 text-purple-500"
      />
      <MetricCard
        icon={HardDrive}
        title="Disk"
        value={`${data.disk.percent}%`}
        subtitle={`${formatBytes(data.disk.used_bytes)} / ${formatBytes(data.disk.total_bytes)}`}
        percent={data.disk.percent}
        color="bg-amber-500/10 text-amber-500"
      />
      <MetricCard
        icon={Network}
        title="Network I/O"
        value={`↑ ${formatBytes(data.network.bytes_sent)}`}
        subtitle={`↓ ${formatBytes(data.network.bytes_recv)} · ${data.network.errors_in + data.network.errors_out} errors`}
        color="bg-emerald-500/10 text-emerald-500"
      />
    </div>
  );
}

// ─── Process List Section ────────────────────────────────────────────────────

function ProcessList({ data }: { data: DebugMonitorProcessesResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Cog className="h-4 w-4" />
          Managed Processes
        </CardTitle>
        <CardDescription>{data.total} processes</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="text-left py-2 pr-4 font-medium">PID</th>
                <th className="text-left py-2 pr-4 font-medium">Name</th>
                <th className="text-left py-2 pr-4 font-medium">Status</th>
                <th className="text-right py-2 pr-4 font-medium">CPU %</th>
                <th className="text-right py-2 pr-4 font-medium">Memory</th>
                <th className="text-right py-2 font-medium">Uptime</th>
              </tr>
            </thead>
            <tbody>
              {data.processes.map((proc) => (
                <tr key={proc.pid} className="border-b last:border-0">
                  <td className="py-2 pr-4 font-mono text-xs">{proc.pid}</td>
                  <td className="py-2 pr-4 font-medium">{proc.name}</td>
                  <td className="py-2 pr-4">
                    <Badge
                      variant={proc.status === "running" ? "success" : proc.status === "sleeping" ? "secondary" : "destructive"}
                    >
                      {proc.status}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4 text-right font-mono text-xs">
                    {proc.cpu_percent.toFixed(1)}%
                  </td>
                  <td className="py-2 pr-4 text-right font-mono text-xs">
                    {formatBytes(proc.memory_rss_bytes)}
                  </td>
                  <td className="py-2 text-right font-mono text-xs">
                    {proc.uptime_seconds ? formatUptime(proc.uptime_seconds) : "—"}
                  </td>
                </tr>
              ))}
              {data.processes.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-muted-foreground">
                    No managed processes found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Request Metrics Section ─────────────────────────────────────────────────

function RequestMetrics({ data }: { data: DebugMonitorMetricsResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4" />
          Request Metrics
        </CardTitle>
        <CardDescription>
          {data.service_running ? "Service running" : "Service stopped"} · v{data.version} · Up {data.service_uptime_formatted}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Total Requests</p>
            <p className="text-2xl font-bold">{data.total_requests.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Total Errors</p>
            <p className="text-2xl font-bold text-destructive">{data.total_errors.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Error Rate</p>
            <p className="text-2xl font-bold">{data.error_rate_percent}%</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">API Uptime</p>
            <p className="text-2xl font-bold">{formatUptime(data.uptime_seconds)}</p>
          </div>
        </div>

        {Object.keys(data.requests_by_status).length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-xs text-muted-foreground mb-2">By Status</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.requests_by_status).map(([status, count]) => (
                <Badge
                  key={status}
                  variant={status === "2xx" ? "success" : status === "4xx" ? "secondary" : "destructive"}
                >
                  {status}: {count.toLocaleString()}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {Object.keys(data.requests_by_method).length > 0 && (
          <div className="mt-3 pt-3 border-t">
            <p className="text-xs text-muted-foreground mb-2">By Method</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.requests_by_method).map(([method, count]) => (
                <Badge key={method} variant="outline">
                  {method}: {count.toLocaleString()}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Error Tracker Section ───────────────────────────────────────────────────

function ErrorTracker({ data }: { data: DebugMonitorErrorsResponse }) {
  const hasErrors = data.total_request_errors > 0 || data.total_log_errors > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4" />
          Errors
          {hasErrors && (
            <Badge variant="destructive" className="ml-auto">
              {data.total_request_errors + data.total_log_errors}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          {data.total_request_errors} request errors · {data.total_log_errors} log errors
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!hasErrors && (
          <p className="text-sm text-muted-foreground text-center py-4">No errors recorded</p>
        )}
        {data.request_errors.length > 0 && (
          <div className="space-y-1 max-h-48 overflow-y-auto">
            <p className="text-xs font-medium text-muted-foreground mb-2">Recent Request Errors</p>
            {data.request_errors.slice(-20).reverse().map((err, i) => (
              <div key={i} className="flex items-center gap-2 text-xs font-mono py-1 border-b last:border-0">
                <Badge variant="destructive" className="text-[10px] px-1.5">{err.status_code}</Badge>
                <span className="text-muted-foreground">{err.method}</span>
                <span className="truncate flex-1">{err.path}</span>
                <span className="text-muted-foreground">{err.duration_ms}ms</span>
              </div>
            ))}
          </div>
        )}
        {data.log_errors.length > 0 && (
          <div className="mt-3 space-y-1 max-h-48 overflow-y-auto">
            <p className="text-xs font-medium text-muted-foreground mb-2">Recent Log Errors</p>
            {data.log_errors.slice(-20).reverse().map((entry, i) => (
              <div key={i} className="text-xs font-mono py-1 border-b last:border-0">
                <div className="flex items-center gap-2">
                  <Badge variant="destructive" className="text-[10px] px-1.5">{entry.level}</Badge>
                  <span className="text-muted-foreground truncate">{entry.logger}</span>
                </div>
                <p className="text-foreground mt-0.5 break-all">{entry.message}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Log Viewer Section ──────────────────────────────────────────────────────

function LogViewer({ data }: { data: DebugMonitorLogsResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ScrollText className="h-4 w-4" />
          Recent Logs
        </CardTitle>
        <CardDescription>{data.total} entries</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="max-h-80 overflow-y-auto space-y-0.5">
          {data.logs.map((entry, i) => (
            <div key={i} className="flex items-start gap-2 text-xs font-mono py-1 border-b last:border-0">
              <Badge
                variant={
                  entry.level === "ERROR" || entry.level === "CRITICAL"
                    ? "destructive"
                    : entry.level === "WARNING"
                      ? "secondary"
                      : "outline"
                }
                className="text-[10px] px-1.5 flex-shrink-0 mt-0.5"
              >
                {entry.level || "—"}
              </Badge>
              <span className="text-muted-foreground flex-shrink-0">
                {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : "—"}
              </span>
              <span className="break-all">{entry.message}</span>
            </div>
          ))}
          {data.logs.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">No log entries</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Skeleton Loaders ────────────────────────────────────────────────────────

function SystemMetricsSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => (
        <Card key={i}>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3 mb-3">
              <Skeleton className="h-8 w-8 rounded-lg" />
              <div className="flex-1">
                <Skeleton className="h-3 w-16 mb-1" />
                <Skeleton className="h-6 w-12" />
              </div>
            </div>
            <Skeleton className="h-2.5 w-full rounded-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function CardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3 w-24" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-32 w-full" />
      </CardContent>
    </Card>
  );
}

// ─── Main Dashboard ──────────────────────────────────────────────────────────

const REFETCH_INTERVAL = 5000;

export function MonitorDashboard() {
  const [logLevel, setLogLevel] = useState<string | undefined>(undefined);

  const systemQuery = useQuery({
    queryKey: ["debug-monitor", "system"],
    queryFn: api.getDebugMonitorSystem,
    refetchInterval: REFETCH_INTERVAL,
    retry: 1,
  });

  const processesQuery = useQuery({
    queryKey: ["debug-monitor", "processes"],
    queryFn: api.getDebugMonitorProcesses,
    refetchInterval: REFETCH_INTERVAL,
    retry: 1,
  });

  const metricsQuery = useQuery({
    queryKey: ["debug-monitor", "metrics"],
    queryFn: api.getDebugMonitorMetrics,
    refetchInterval: REFETCH_INTERVAL,
    retry: 1,
  });

  const errorsQuery = useQuery({
    queryKey: ["debug-monitor", "errors"],
    queryFn: api.getDebugMonitorErrors,
    refetchInterval: REFETCH_INTERVAL,
    retry: 1,
  });

  const logsQuery = useQuery({
    queryKey: ["debug-monitor", "logs", logLevel],
    queryFn: () => api.getDebugMonitorLogs(logLevel, 200),
    refetchInterval: REFETCH_INTERVAL,
    retry: 1,
  });

  const isLoading = systemQuery.isLoading && metricsQuery.isLoading;

  const refetchAll = () => {
    systemQuery.refetch();
    processesQuery.refetch();
    metricsQuery.refetch();
    errorsQuery.refetch();
    logsQuery.refetch();
  };

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="success" className="animate-pulse">
            Live
          </Badge>
          <span className="text-sm text-muted-foreground">
            Auto-refreshing every {REFETCH_INTERVAL / 1000}s
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={refetchAll} disabled={isLoading}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* System Metrics */}
      <div className="animate-card-fade-in" style={{ animationDelay: "0ms" }}>
        {systemQuery.data ? (
          <SystemMetrics data={systemQuery.data} />
        ) : systemQuery.isLoading ? (
          <SystemMetricsSkeleton />
        ) : systemQuery.isError ? (
          <Card>
            <CardContent className="py-8 text-center text-destructive">
              Failed to load system metrics: {(systemQuery.error as Error)?.message}
            </CardContent>
          </Card>
        ) : null}
      </div>

      {/* Request Metrics */}
      <div className="animate-card-fade-in" style={{ animationDelay: "100ms" }}>
        {metricsQuery.data ? (
          <RequestMetrics data={metricsQuery.data} />
        ) : metricsQuery.isLoading ? (
          <CardSkeleton />
        ) : null}
      </div>

      {/* Process List + Errors */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-card-fade-in" style={{ animationDelay: "200ms" }}>
        {processesQuery.data ? (
          <ProcessList data={processesQuery.data} />
        ) : processesQuery.isLoading ? (
          <CardSkeleton />
        ) : null}

        {errorsQuery.data ? (
          <ErrorTracker data={errorsQuery.data} />
        ) : errorsQuery.isLoading ? (
          <CardSkeleton />
        ) : null}
      </div>

      {/* Log Viewer */}
      <div className="animate-card-fade-in" style={{ animationDelay: "300ms" }}>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-medium">Filter:</span>
          {["All", "ERROR", "WARNING", "INFO", "DEBUG"].map((lvl) => {
            const value = lvl === "All" ? undefined : lvl;
            return (
              <Button
                key={lvl}
                variant={logLevel === value ? "default" : "outline"}
                size="sm"
                onClick={() => setLogLevel(value)}
                className="text-xs h-7 px-2"
              >
                {lvl}
              </Button>
            );
          })}
        </div>
        {logsQuery.data ? (
          <LogViewer data={logsQuery.data} />
        ) : logsQuery.isLoading ? (
          <CardSkeleton />
        ) : null}
      </div>
    </div>
  );
}
