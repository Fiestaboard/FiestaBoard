"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { 
  Bug, 
  Trash2, 
  TestTube, 
  Info, 
  Wifi, 
  Database, 
  ChevronDown, 
  ChevronUp,
  Loader2,
  CheckCircle,
  XCircle,
  AlertCircle,
  Globe,
  Server,
  Lightbulb
} from "lucide-react";
import { api } from "@/lib/api";
import type { NetworkDiagnosticsResult } from "@/lib/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

// Character code definitions matching board_chars.py
const CHARACTER_GROUPS = {
  Letters: Array.from({ length: 26 }, (_, i) => ({
    code: i + 1,
    label: String.fromCharCode(65 + i),
    display: `${String.fromCharCode(65 + i)} (${i + 1})`
  })),
  Numbers: [
    { code: 27, label: "1", display: "1 (27)" },
    { code: 28, label: "2", display: "2 (28)" },
    { code: 29, label: "3", display: "3 (29)" },
    { code: 30, label: "4", display: "4 (30)" },
    { code: 31, label: "5", display: "5 (31)" },
    { code: 32, label: "6", display: "6 (32)" },
    { code: 33, label: "7", display: "7 (33)" },
    { code: 34, label: "8", display: "8 (34)" },
    { code: 35, label: "9", display: "9 (35)" },
    { code: 36, label: "0", display: "0 (36)" },
  ],
  Symbols: [
    { code: 0, label: "Space", display: "Space (0)" },
    { code: 37, label: "!", display: "! (37)" },
    { code: 38, label: "@", display: "@ (38)" },
    { code: 39, label: "#", display: "# (39)" },
    { code: 40, label: "$", display: "$ (40)" },
    { code: 41, label: "(", display: "( (41)" },
    { code: 42, label: ")", display: ") (42)" },
    { code: 44, label: "-", display: "- (44)" },
    { code: 47, label: "&", display: "& (47)" },
    { code: 48, label: "=", display: "= (48)" },
    { code: 49, label: ";", display: "; (49)" },
    { code: 50, label: ":", display: ": (50)" },
    { code: 52, label: "'", display: "' (52)" },
    { code: 53, label: '"', display: "\" (53)" },
    { code: 54, label: "%", display: "% (54)" },
    { code: 55, label: ",", display: ", (55)" },
    { code: 56, label: ".", display: ". (56)" },
    { code: 59, label: "/", display: "/ (59)" },
    { code: 60, label: "?", display: "? (60)" },
    { code: 62, label: "°", display: "° (62)" },
  ],
  Colors: [
    { code: 63, label: "Red", display: "Red (63)" },
    { code: 64, label: "Orange", display: "Orange (64)" },
    { code: 65, label: "Yellow", display: "Yellow (65)" },
    { code: 66, label: "Green", display: "Green (66)" },
    { code: 67, label: "Blue", display: "Blue (67)" },
    { code: 68, label: "Violet", display: "Violet (68)" },
    { code: 69, label: "White", display: "White (69)" },
    { code: 70, label: "Black", display: "Black (70)" },
  ],
};

export function DebugSettings() {
  const queryClient = useQueryClient();
  const [selectedCharacter, setSelectedCharacter] = useState<number>(63); // Default to Red
  const [showSystemInfo, setShowSystemInfo] = useState(false);

  // Fetch system info
  const { data: systemInfo, isLoading: isLoadingSystemInfo } = useQuery({
    queryKey: ["debug-system-info"],
    queryFn: api.getDebugSystemInfo,
    refetchInterval: showSystemInfo ? 10000 : false, // Auto-refresh every 10s when expanded
  });

  // Fetch cache status
  const { data: cacheStatus, refetch: refetchCacheStatus } = useQuery({
    queryKey: ["debug-cache-status"],
    queryFn: api.getBoardCacheStatus,
    enabled: showSystemInfo,
    refetchInterval: showSystemInfo ? 10000 : false,
  });

  // Blank board mutation
  const blankMutation = useMutation({
    mutationFn: api.blankBoard,
    onSuccess: (data) => {
      toast.success(data.message);
    },
    onError: (error: Error) => {
      toast.error(`Failed to blank board: ${error.message}`);
    },
  });

  // Fill board mutation
  const fillMutation = useMutation({
    mutationFn: (code: number) => api.fillBoard(code),
    onSuccess: (data) => {
      toast.success(data.message);
    },
    onError: (error: Error) => {
      toast.error(`Failed to fill board: ${error.message}`);
    },
  });

  // Show debug info mutation
  const debugInfoMutation = useMutation({
    mutationFn: api.showDebugInfo,
    onSuccess: (data) => {
      toast.success(data.message);
      if (data.debug_info) {
        console.log("Debug info sent:", data.debug_info);
      }
    },
    onError: (error: Error) => {
      toast.error(`Failed to show debug info: ${error.message}`);
    },
  });

  // Network diagnostics mutation
  const networkDiagnosticsMutation = useMutation({
    mutationFn: async () => {
      const response = await api.getNetworkDiagnostics();
      return response.diagnostics;
    },
    onSuccess: (data: NetworkDiagnosticsResult) => {
      if (data.overall_ok) {
        toast.success("All network checks passed!");
      } else {
        toast.error("Some network checks failed — see details below");
      }
    },
    onError: (error: Error) => {
      toast.error(`Network diagnostics failed: ${error.message}`);
    },
  });

  // Clear cache mutation
  const clearCacheMutation = useMutation({
    mutationFn: api.clearBoardCache,
    onSuccess: (data) => {
      toast.success(data.message);
      refetchCacheStatus();
      queryClient.invalidateQueries({ queryKey: ["debug-cache-status"] });
    },
    onError: (error: Error) => {
      toast.error(`Failed to clear cache: ${error.message}`);
    },
  });

  const isAnyMutationLoading = 
    blankMutation.isPending ||
    fillMutation.isPending ||
    debugInfoMutation.isPending ||
    networkDiagnosticsMutation.isPending ||
    clearCacheMutation.isPending;

  const isBoardConfigured = systemInfo?.board_configured ?? false;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-md bg-primary/10">
              <Bug className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                Debug Tools
                {isBoardConfigured ? (
                  <Badge variant="default" className="text-xs bg-board-green">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    Ready
                  </Badge>
                ) : (
                  <Badge variant="destructive" className="text-xs">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    Not Configured
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Test and debug Vestaboard connection
              </CardDescription>
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Network Diagnostics */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Network Diagnostics</Label>
          <Button
            onClick={() => networkDiagnosticsMutation.mutate()}
            disabled={isAnyMutationLoading}
            variant="outline"
            size="sm"
            className="w-full justify-start gap-2"
          >
            {networkDiagnosticsMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Wifi className="h-4 w-4" />
            )}
            {networkDiagnosticsMutation.isPending ? "Running diagnostics…" : "Run Network Diagnostics"}
          </Button>
          <p className="text-xs text-muted-foreground">
            Tests DNS, internet connectivity, and Vestaboard reachability
          </p>

          {/* Diagnostics Results */}
          {networkDiagnosticsMutation.data && (
            <div className="space-y-2 mt-2">
              {/* Overall Status Banner */}
              <div className={`flex items-center gap-2 text-sm font-medium p-2.5 rounded-md ${
                networkDiagnosticsMutation.data.overall_ok
                  ? "bg-success/10 text-success"
                  : "bg-destructive/10 text-foreground"
              }`}>
                {networkDiagnosticsMutation.data.overall_ok ? (
                  <CheckCircle className="h-4 w-4 flex-shrink-0" />
                ) : (
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                )}
                {networkDiagnosticsMutation.data.overall_ok
                  ? "All checks passed — your connection is healthy"
                  : "Some checks failed — see details below"}
              </div>

              {/* Step-by-step results */}
              <div className="rounded-md border divide-y">
                {/* DNS Check */}
                <DiagnosticRow
                  icon={<Globe className="h-3.5 w-3.5" />}
                  label="DNS Resolution"
                  result={networkDiagnosticsMutation.data.dns}
                  detail={networkDiagnosticsMutation.data.dns.ok
                    ? `Resolved ${networkDiagnosticsMutation.data.dns.hostname ?? "google.com"} → ${networkDiagnosticsMutation.data.dns.ip}`
                    : networkDiagnosticsMutation.data.dns.error ?? "Could not resolve hostname"
                  }
                />

                {/* Internet Check */}
                <DiagnosticRow
                  icon={<Wifi className="h-3.5 w-3.5" />}
                  label="Internet Access"
                  result={networkDiagnosticsMutation.data.internet}
                  detail={networkDiagnosticsMutation.data.internet.ok
                    ? `Reached ${networkDiagnosticsMutation.data.internet.url ?? "google.com"}${networkDiagnosticsMutation.data.internet.latency_ms != null ? ` (${networkDiagnosticsMutation.data.internet.latency_ms}ms)` : ""}`
                    : networkDiagnosticsMutation.data.internet.error ?? "Could not reach the internet"
                  }
                />

                {/* Vestaboard Check */}
                <VestaboardDiagnosticRow
                  vestaboard={networkDiagnosticsMutation.data.vestaboard}
                />
              </div>

              {/* Troubleshooting Recommendations */}
              {networkDiagnosticsMutation.data.recommendations.length > 0 &&
                !networkDiagnosticsMutation.data.overall_ok && (
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <Lightbulb className="h-3.5 w-3.5" />
                    Troubleshooting
                  </div>
                  {networkDiagnosticsMutation.data.recommendations.map((rec, i) => (
                    <div key={i} className="rounded-md border p-3 space-y-1.5 bg-muted/30">
                      <div className="text-xs font-medium">{rec.summary}</div>
                      {rec.steps.length > 0 && (
                        <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
                          {rec.steps.map((step, j) => (
                            <li key={j}>{step}</li>
                          ))}
                        </ol>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Blank Board */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Clear Board</Label>
          <Button
            onClick={() => blankMutation.mutate()}
            disabled={!isBoardConfigured || isAnyMutationLoading}
            variant="outline"
            size="sm"
            className="w-full justify-start gap-2"
          >
            {blankMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Blank Board
          </Button>
          <p className="text-xs text-muted-foreground">
            Fill the board with blank spaces
          </p>
        </div>

        {/* Fill Board with Character */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Fill with Character</Label>
          <div className="flex gap-2">
            <Select
              value={selectedCharacter.toString()}
              onValueChange={(value) => setSelectedCharacter(parseInt(value))}
            >
              <SelectTrigger className="flex-1 h-9 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-80">
                {Object.entries(CHARACTER_GROUPS).map(([group, chars]) => (
                  <div key={group}>
                    <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                      {group}
                    </div>
                    {chars.map((char) => (
                      <SelectItem 
                        key={char.code} 
                        value={char.code.toString()}
                        className="text-xs font-mono"
                      >
                        {char.display}
                      </SelectItem>
                    ))}
                  </div>
                ))}
              </SelectContent>
            </Select>
            <Button
              onClick={() => fillMutation.mutate(selectedCharacter)}
              disabled={!isBoardConfigured || isAnyMutationLoading}
              variant="outline"
              size="sm"
              className="gap-2"
            >
              {fillMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <TestTube className="h-4 w-4" />
              )}
              Fill
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Fill entire board with selected character
          </p>
        </div>

        {/* Show Debug Info */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Display System Info</Label>
          <Button
            onClick={() => debugInfoMutation.mutate()}
            disabled={!isBoardConfigured || isAnyMutationLoading}
            variant="outline"
            size="sm"
            className="w-full justify-start gap-2"
          >
            {debugInfoMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Info className="h-4 w-4" />
            )}
            Show Debug Info on Board
          </Button>
          <p className="text-xs text-muted-foreground">
            Display system information on the board
          </p>
        </div>

        {/* Clear Cache */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Cache Management</Label>
          <Button
            onClick={() => clearCacheMutation.mutate()}
            disabled={!isBoardConfigured || isAnyMutationLoading}
            variant="outline"
            size="sm"
            className="w-full justify-start gap-2"
          >
            {clearCacheMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Database className="h-4 w-4" />
            )}
            Clear Message Cache
          </Button>
          <p className="text-xs text-muted-foreground">
            Force next message to send regardless of content
          </p>
        </div>

        {/* System Info Collapsible */}
        <div className="pt-2 border-t">
          <Collapsible open={showSystemInfo} onOpenChange={setShowSystemInfo}>
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between text-xs font-medium"
              >
                <span>System Information</span>
                {showSystemInfo ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3 space-y-3">
              {isLoadingSystemInfo ? (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-full" />
                </div>
              ) : systemInfo ? (
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2 p-2 rounded bg-muted/50">
                    <div className="font-medium text-muted-foreground">Board IP:</div>
                    <div className="font-mono">{systemInfo.board_ip || "Not set"}</div>
                    
                    <div className="font-medium text-muted-foreground">Server IP:</div>
                    <div className="font-mono">{systemInfo.server_ip}</div>
                    
                    <div className="font-medium text-muted-foreground">Connection:</div>
                    <div className="font-mono">{systemInfo.connection_mode.toUpperCase()} API</div>
                    
                    <div className="font-medium text-muted-foreground">Uptime:</div>
                    <div className="font-mono">{systemInfo.uptime_formatted}</div>
                    
                    <div className="font-medium text-muted-foreground">Version:</div>
                    <div className="font-mono">v{systemInfo.version}</div>
                    
                    <div className="font-medium text-muted-foreground">Service:</div>
                    <div className="flex items-center gap-1">
                      {systemInfo.service_running ? (
                        <>
                          <div className="h-2 w-2 rounded-full bg-success" />
                          <span>Running</span>
                        </>
                      ) : (
                        <>
                          <div className="h-2 w-2 rounded-full bg-destructive" />
                          <span>Stopped</span>
                        </>
                      )}
                    </div>
                    
                    <div className="font-medium text-muted-foreground">Dev Mode:</div>
                    <div>{systemInfo.dev_mode ? "Enabled" : "Disabled"}</div>
                  </div>

                  {/* Cache Status */}
                  {systemInfo.cache_status && (
                    <div className="p-2 rounded bg-muted/50">
                      <div className="font-medium text-muted-foreground mb-2">Cache Status:</div>
                      <div className="space-y-1 ml-2">
                        <div className="flex items-center gap-2">
                          <div className={`h-2 w-2 rounded-full ${
                            systemInfo.cache_status.has_cached_text || 
                            systemInfo.cache_status.has_cached_characters 
                              ? "bg-info" 
                              : "bg-muted-foreground"
                          }`} />
                          <span>
                            {systemInfo.cache_status.has_cached_text 
                              ? "Text cached" 
                              : systemInfo.cache_status.has_cached_characters
                              ? "Characters cached"
                              : "No cache"}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">Skip unchanged:</span>
                          <span>{systemInfo.cache_status.skip_unchanged_enabled ? "Yes" : "No"}</span>
                        </div>
                        {systemInfo.cache_status.cached_text_preview && (
                          <div className="mt-2">
                            <div className="text-muted-foreground">Preview:</div>
                            <div className="font-mono text-xs mt-1 p-1 bg-background rounded">
                              {systemInfo.cache_status.cached_text_preview}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="text-xs text-muted-foreground text-center pt-1">
                    Auto-refreshes every 10 seconds
                  </div>
                </div>
              ) : (
                <div className="text-xs text-center text-muted-foreground">
                  No system info available
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>
        </div>

        {/* Warning message if not configured */}
        {!isBoardConfigured && (
          <div className="flex items-start gap-2 p-2 rounded-md bg-muted text-foreground text-xs">
            <Info className="h-4 w-4 mt-0.5 flex-shrink-0" />
            <div>
              <div className="font-medium">Board not configured</div>
              <div className="text-xs mt-0.5">
                Network diagnostics can still be run to test DNS and internet connectivity. Configure your board connection above to enable the other debug tools.
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Helper sub-components for network diagnostics
// ---------------------------------------------------------------------------

function DiagnosticStatusIcon({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle className="h-3.5 w-3.5 text-success flex-shrink-0" />
  ) : (
    <XCircle className="h-3.5 w-3.5 text-destructive flex-shrink-0" />
  );
}

function DiagnosticRow({
  icon,
  label,
  result,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  result: { ok: boolean; latency_ms?: number };
  detail: string;
}) {
  return (
    <div className="flex items-start gap-2 p-2.5 text-xs">
      <DiagnosticStatusIcon ok={result.ok} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 font-medium">
          {icon}
          {label}
          {result.latency_ms != null && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 font-mono">
              {result.latency_ms}ms
            </Badge>
          )}
        </div>
        <div className={`mt-0.5 ${result.ok ? "text-muted-foreground" : "text-destructive"}`}>
          {detail}
        </div>
      </div>
    </div>
  );
}

function VestaboardDiagnosticRow({
  vestaboard,
}: {
  vestaboard: {
    ok: boolean;
    mode: "local" | "cloud" | null;
    steps: Record<string, { ok: boolean; latency_ms?: number; status_code?: number | null; error?: string; hostname?: string; port?: number }>;
    error?: string;
  };
}) {
  if (vestaboard.mode === null) {
    return (
      <div className="flex items-start gap-2 p-2.5 text-xs">
        <AlertCircle className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 font-medium">
            <Server className="h-3.5 w-3.5" />
            Vestaboard
          </div>
          <div className="mt-0.5 text-muted-foreground">
            {vestaboard.error ?? "No board configured"}
          </div>
        </div>
      </div>
    );
  }

  if (vestaboard.mode === "cloud") {
    const cloud = vestaboard.steps.cloud_api;
    return (
      <div className="flex items-start gap-2 p-2.5 text-xs">
        <DiagnosticStatusIcon ok={vestaboard.ok} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 font-medium">
            <Server className="h-3.5 w-3.5" />
            Vestaboard Cloud API
            {cloud?.latency_ms != null && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 font-mono">
                {cloud.latency_ms}ms
              </Badge>
            )}
          </div>
          <div className={`mt-0.5 ${vestaboard.ok ? "text-muted-foreground" : "text-destructive"}`}>
            {vestaboard.ok
              ? `Cloud API reachable${cloud?.status_code ? ` (HTTP ${cloud.status_code})` : ""}`
              : cloud?.error ?? (cloud?.status_code ? `HTTP ${cloud.status_code}` : "Could not reach cloud API")}
          </div>
        </div>
      </div>
    );
  }

  // Local mode — show sub-steps
  const steps = vestaboard.steps;
  const stepEntries: { key: string; label: string; icon: React.ReactNode }[] = [
    { key: "dns", label: "Board DNS", icon: <Globe className="h-3 w-3" /> },
    { key: "port", label: "Board Port", icon: <Server className="h-3 w-3" /> },
    { key: "api", label: "Board API", icon: <Wifi className="h-3 w-3" /> },
  ];

  return (
    <div className="p-2.5 text-xs space-y-1.5">
      <div className="flex items-center gap-2">
        <DiagnosticStatusIcon ok={vestaboard.ok} />
        <div className="flex items-center gap-1.5 font-medium">
          <Server className="h-3.5 w-3.5" />
          Vestaboard (Local API)
        </div>
      </div>
      <div className="space-y-1 pl-1 border-l-2 border-muted ml-[11px]">
        {stepEntries.map(({ key, label, icon }) => {
          const step = steps[key];
          if (!step) {
            // Step wasn't reached (short-circuited)
            return (
              <div key={key} className="flex items-center gap-1.5 pl-2 py-0.5 text-muted-foreground">
                <div className="h-3 w-3 rounded-full border border-muted-foreground/30 flex-shrink-0" />
                {icon}
                <span>{label}</span>
                <span className="text-muted-foreground/60">— skipped</span>
              </div>
            );
          }
          return (
            <div key={key} className="flex items-start gap-1.5 pl-2 py-0.5">
              <DiagnosticStatusIcon ok={step.ok} />
              {icon}
              <div className="min-w-0">
                <span className="font-medium">{label}</span>
                {step.latency_ms != null && (
                  <Badge variant="secondary" className="ml-1 text-[10px] px-1 py-0 h-3.5 font-mono">
                    {step.latency_ms}ms
                  </Badge>
                )}
                {step.ok ? (
                  <span className="text-muted-foreground ml-1">
                    {key === "dns" && step.hostname ? `${step.hostname} resolved` : ""}
                    {key === "port" && step.port ? `port ${step.port} open` : ""}
                    {key === "api" && step.status_code ? `HTTP ${step.status_code}` : ""}
                  </span>
                ) : (
                  <span className="text-destructive ml-1">
                    {step.error ?? (step.status_code ? `HTTP ${step.status_code}` : "failed")}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
