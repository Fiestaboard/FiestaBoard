"use client";

import {
  Badge,
  Box,
  Button,
  Card,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Flex,
  Grid,
  Label,
  List,
  ListItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bug,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Database,
  Globe,
  Info,
  Lightbulb,
  Loader2,
  Server,
  TestTube,
  Trash2,
  Wifi,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import type { NetworkDiagnosticsResult } from "@/lib/api";
import { api } from "@/lib/api";

// Character code definitions matching board_chars.py
const CHARACTER_GROUPS = {
  Letters: Array.from({ length: 26 }, (_, i) => ({
    code: i + 1,
    label: String.fromCharCode(65 + i),
    display: `${String.fromCharCode(65 + i)} (${i + 1})`,
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
    { code: 53, label: '"', display: '" (53)' },
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
  const t = useTranslations("debugSettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selectedCharacter, setSelectedCharacter] = useState<number>(63); // Default to Red
  const [showSystemInfo, setShowSystemInfo] = useState(false);

  // Fetch system info
  const { data: systemInfo, isLoading: isLoadingSystemInfo } = useQuery({
    queryKey: ["debug-system-info"],
    queryFn: api.getDebugSystemInfo,
    refetchInterval: showSystemInfo ? 10000 : false, // Auto-refresh every 10s when expanded
  });

  // Fetch cache status
  const { data: _cacheStatus, refetch: refetchCacheStatus } = useQuery({
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
      queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error: Error) => {
      toast.error(t("toastBlankFailed", { error: error.message }));
    },
  });

  // Fill board mutation
  const fillMutation = useMutation({
    mutationFn: (code: number) => api.fillBoard(code),
    onSuccess: (data) => {
      toast.success(data.message);
      queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error: Error) => {
      toast.error(t("toastFillFailed", { error: error.message }));
    },
  });

  // Show debug info mutation
  const debugInfoMutation = useMutation({
    mutationFn: api.showDebugInfo,
    onSuccess: (data) => {
      toast.success(data.message);
      queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error: Error) => {
      toast.error(t("toastDebugInfoFailed", { error: error.message }));
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
        toast.success(t("toastNetworkSuccess"));
      } else {
        toast.error(t("toastNetworkFailed"));
      }
    },
    onError: (error: Error) => {
      toast.error(t("toastNetworkError", { error: error.message }));
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
      toast.error(t("toastCacheClearFailed", { error: error.message }));
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
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card>
        <CollapsibleTrigger className="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset">
          <Flex align="center" gap="2">
            <Bug className="h-4 w-4 text-muted-foreground" />
            <Text as="span" size="base" weight="semibold">
              {t("title")}
            </Text>
            {!isBoardConfigured && (
              <Badge variant="destructive" className="text-xs">
                <AlertCircle className="h-3 w-3 mr-1" />
                {t("boardNotConfiguredTitle")}
              </Badge>
            )}
          </Flex>
          <ChevronDown
            className={`h-5 w-5 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          />
        </CollapsibleTrigger>

        <CollapsibleContent>
          <Stack gap="4" className="px-6 pb-4 pt-1">
            <Text tone="muted">{t("description")}</Text>
            <Stack gap="4">
              {/* Network Diagnostics */}
              <Stack gap="2">
                <Text size="xs" weight="medium">
                  {t("networkDiagnosticsLabel")}
                </Text>
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
                  {networkDiagnosticsMutation.isPending ? t("runningDiagnostics") : t("runNetworkDiagnostics")}
                </Button>
                <Text size="xs" tone="muted">
                  {t("diagnosticsDescription")}
                </Text>

                {/* Diagnostics Results */}
                {networkDiagnosticsMutation.data && (
                  <Stack gap="2" className="mt-2">
                    {/* Overall Status Banner */}
                    <Flex
                      align="center"
                      gap="2"
                      className={`text-sm font-medium p-2.5 rounded-md ${
                        networkDiagnosticsMutation.data.overall_ok
                          ? "bg-success/10 text-success"
                          : "bg-destructive/10 text-foreground"
                      }`}
                    >
                      {networkDiagnosticsMutation.data.overall_ok ? (
                        <CheckCircle className="h-4 w-4 flex-shrink-0" />
                      ) : (
                        <AlertCircle className="h-4 w-4 flex-shrink-0" />
                      )}
                      {networkDiagnosticsMutation.data.overall_ok ? t("allChecksPassed") : t("someChecksFailed")}
                    </Flex>

                    {/* Step-by-step results */}
                    <Box className="rounded-md border divide-y">
                      {/* DNS Check */}
                      <DiagnosticRow
                        icon={<Globe className="h-3.5 w-3.5" />}
                        label={t("dnsResolution")}
                        result={networkDiagnosticsMutation.data.dns}
                        detail={
                          networkDiagnosticsMutation.data.dns.ok
                            ? t("resolved", {
                                hostname: networkDiagnosticsMutation.data.dns.hostname ?? "google.com",
                                ip: networkDiagnosticsMutation.data.dns.ip ?? "",
                              })
                            : (networkDiagnosticsMutation.data.dns.error ?? t("couldNotResolve"))
                        }
                      />

                      {/* Internet Check */}
                      <DiagnosticRow
                        icon={<Wifi className="h-3.5 w-3.5" />}
                        label={t("internetAccess")}
                        result={networkDiagnosticsMutation.data.internet}
                        detail={
                          networkDiagnosticsMutation.data.internet.ok
                            ? t("reached", { url: networkDiagnosticsMutation.data.internet.url ?? "google.com" }) +
                              (networkDiagnosticsMutation.data.internet.latency_ms != null
                                ? ` (${networkDiagnosticsMutation.data.internet.latency_ms}ms)`
                                : "")
                            : (networkDiagnosticsMutation.data.internet.error ?? t("couldNotReach"))
                        }
                      />

                      {/* Vestaboard Check */}
                      <VestaboardDiagnosticRow vestaboard={networkDiagnosticsMutation.data.vestaboard} />
                    </Box>

                    {/* Troubleshooting Recommendations */}
                    {networkDiagnosticsMutation.data.recommendations.length > 0 &&
                      !networkDiagnosticsMutation.data.overall_ok && (
                        <Stack gap="2">
                          <Flex align="center" gap="1.5" className="text-xs font-medium text-muted-foreground">
                            <Lightbulb className="h-3.5 w-3.5" />
                            {t("troubleshooting")}
                          </Flex>
                          {networkDiagnosticsMutation.data.recommendations.map((rec, i) => (
                            <Stack key={i} gap="1.5" className="rounded-md border p-3 bg-muted/30">
                              <Text size="xs" weight="medium">
                                {rec.summary}
                              </Text>
                              {rec.steps.length > 0 && (
                                <List
                                  as="ol"
                                  marker="decimal"
                                  gap="1"
                                  className="text-xs text-muted-foreground list-inside"
                                >
                                  {rec.steps.map((step, j) => (
                                    <ListItem key={j}>{step}</ListItem>
                                  ))}
                                </List>
                              )}
                            </Stack>
                          ))}
                        </Stack>
                      )}
                  </Stack>
                )}
              </Stack>

              {/* Blank Board */}
              <Stack gap="2">
                <Text size="xs" weight="medium">
                  {t("clearBoardLabel")}
                </Text>
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
                  {t("blankBoard")}
                </Button>
                <Text size="xs" tone="muted">
                  {t("blankBoardDescription")}
                </Text>
              </Stack>

              {/* Fill Board with Character */}
              <Stack gap="2">
                <Label htmlFor="fill-character" className="text-xs font-medium">
                  {t("fillWithCharacterLabel")}
                </Label>
                <Flex gap="2">
                  <Select
                    value={selectedCharacter.toString()}
                    onValueChange={(value) => setSelectedCharacter(parseInt(value))}
                  >
                    <SelectTrigger id="fill-character" className="flex-1 h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="max-h-80">
                      {Object.entries(CHARACTER_GROUPS).map(([group, chars]) => (
                        <Box key={group}>
                          <Text weight="semibold" tone="muted" className="px-2 py-1.5 text-xs">
                            {t(`groups.${group}` as "groups.Letters")}
                          </Text>
                          {chars.map((char) => (
                            <SelectItem key={char.code} value={char.code.toString()} className="text-xs font-mono">
                              {char.display}
                            </SelectItem>
                          ))}
                        </Box>
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
                    {t("fillButton")}
                  </Button>
                </Flex>
                <Text size="xs" tone="muted">
                  {t("fillBoardDescription")}
                </Text>
              </Stack>

              {/* Show Debug Info */}
              <Stack gap="2">
                <Text size="xs" weight="medium">
                  {t("displaySystemInfoLabel")}
                </Text>
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
                <Text size="xs" tone="muted">
                  {t("showDebugInfoDescription")}
                </Text>
              </Stack>

              {/* Clear Cache */}
              <Stack gap="2">
                <Text size="xs" weight="medium">
                  {t("cacheManagementLabel")}
                </Text>
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
                <Text size="xs" tone="muted">
                  {t("clearCacheDescription")}
                </Text>
              </Stack>

              {/* System Info Collapsible */}
              <Box className="pt-2 border-t">
                <Collapsible open={showSystemInfo} onOpenChange={setShowSystemInfo}>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="w-full justify-between text-xs font-medium">
                      <Text as="span" size="xs" weight="medium">
                        {t("systemInformation")}
                      </Text>
                      {showSystemInfo ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-3 space-y-3">
                    {isLoadingSystemInfo ? (
                      <Stack gap="2">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-full" />
                      </Stack>
                    ) : systemInfo ? (
                      <Stack gap="2" className="text-xs">
                        <Grid cols="2" gap="2" className="p-2 rounded bg-muted/50">
                          <Text size="xs" weight="medium" tone="muted">
                            {t("boardIpLabel")}
                          </Text>
                          <Text size="xs" className="font-mono">
                            {systemInfo.board_ip || t("notSet")}
                          </Text>

                          <Text size="xs" weight="medium" tone="muted">
                            {t("serverIpLabel")}
                          </Text>
                          <Text size="xs" className="font-mono">
                            {systemInfo.server_ip}
                          </Text>

                          <Text size="xs" weight="medium" tone="muted">
                            {t("connectionLabel")}
                          </Text>
                          <Text size="xs" className="font-mono">
                            {systemInfo.connection_mode.toUpperCase()} {t("apiSuffix")}
                          </Text>

                          <Text size="xs" weight="medium" tone="muted">
                            {t("uptimeLabel")}
                          </Text>
                          <Text size="xs" className="font-mono">
                            {systemInfo.uptime_formatted}
                          </Text>

                          <Text size="xs" weight="medium" tone="muted">
                            {t("versionLabel")}
                          </Text>
                          <Text size="xs" className="font-mono">
                            v{systemInfo.version}
                          </Text>

                          <Text size="xs" weight="medium" tone="muted">
                            {t("serviceLabel")}
                          </Text>
                          <Flex align="center" gap="1">
                            {systemInfo.service_running ? (
                              <>
                                <Box className="h-2 w-2 rounded-full bg-success" />
                                <Text as="span" size="xs">
                                  {t("serviceRunning")}
                                </Text>
                              </>
                            ) : (
                              <>
                                <Box className="h-2 w-2 rounded-full bg-destructive" />
                                <Text as="span" size="xs">
                                  {t("serviceStopped")}
                                </Text>
                              </>
                            )}
                          </Flex>
                        </Grid>

                        {/* Cache Status */}
                        {systemInfo.cache_status && (
                          <Box className="p-2 rounded bg-muted/50">
                            <Text size="xs" weight="medium" tone="muted" className="mb-2">
                              {t("cacheStatusLabel")}
                            </Text>
                            <Stack gap="1" className="ml-2">
                              <Flex align="center" gap="2">
                                <Box
                                  className={`h-2 w-2 rounded-full ${
                                    systemInfo.cache_status.has_cached_text ||
                                    systemInfo.cache_status.has_cached_characters
                                      ? "bg-info"
                                      : "bg-muted-foreground"
                                  }`}
                                />
                                <Text as="span" size="xs">
                                  {systemInfo.cache_status.has_cached_text
                                    ? t("textCached")
                                    : systemInfo.cache_status.has_cached_characters
                                      ? "Characters cached"
                                      : t("noCache")}
                                </Text>
                              </Flex>
                              <Flex align="center" gap="2">
                                <Text as="span" size="xs" tone="muted">
                                  {t("skipUnchanged")}
                                </Text>
                                <Text as="span" size="xs">
                                  {systemInfo.cache_status.skip_unchanged_enabled ? tCommon("yes") : tCommon("no")}
                                </Text>
                              </Flex>
                              {systemInfo.cache_status.cached_text_preview && (
                                <Box className="mt-2">
                                  <Text size="xs" tone="muted">
                                    {t("cachePreviewLabel")}
                                  </Text>
                                  <Text size="xs" className="font-mono mt-1 p-1 bg-background rounded">
                                    {systemInfo.cache_status.cached_text_preview}
                                  </Text>
                                </Box>
                              )}
                            </Stack>
                          </Box>
                        )}

                        <Text size="xs" tone="muted" className="text-center pt-1">
                          {t("autoRefreshNote")}
                        </Text>
                      </Stack>
                    ) : (
                      <Text size="xs" tone="muted" className="text-center">
                        {t("noSystemInfo")}
                      </Text>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              </Box>

              {/* Warning message if not configured */}
              {!isBoardConfigured && (
                <Flex align="start" gap="2" className="p-2 rounded-md bg-muted text-foreground text-xs">
                  <Info className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <Box>
                    <Text size="xs" weight="medium">
                      {t("boardNotConfiguredTitle")}
                    </Text>
                    <Text size="xs" className="mt-0.5">
                      {t("boardNotConfiguredDescription")}
                    </Text>
                  </Box>
                </Flex>
              )}
            </Stack>
          </Stack>
        </CollapsibleContent>
      </Card>
    </Collapsible>
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
    <Flex align="start" gap="2" className="p-2.5 text-xs">
      <DiagnosticStatusIcon ok={result.ok} />
      <Box className="min-w-0 flex-1">
        <Flex align="center" gap="1.5" className="font-medium">
          {icon}
          {label}
          {result.latency_ms != null && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 font-mono">
              {result.latency_ms}ms
            </Badge>
          )}
        </Flex>
        <Text size="xs" tone={result.ok ? "muted" : "destructive"} className="mt-0.5">
          {detail}
        </Text>
      </Box>
    </Flex>
  );
}

function VestaboardDiagnosticRow({
  vestaboard,
}: {
  vestaboard: {
    ok: boolean;
    mode: "local" | "cloud" | null;
    steps: Record<
      string,
      {
        ok: boolean;
        latency_ms?: number;
        status_code?: number | null;
        error?: string;
        hostname?: string;
        port?: number;
      }
    >;
    error?: string;
  };
}) {
  const t = useTranslations("debugSettings");
  if (vestaboard.mode === null) {
    return (
      <Flex align="start" gap="2" className="p-2.5 text-xs">
        <AlertCircle className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        <Box className="min-w-0 flex-1">
          <Flex align="center" gap="1.5" className="font-medium">
            <Server className="h-3.5 w-3.5" />
            {t("vestaboardLabel")}
          </Flex>
          <Text size="xs" tone="muted" className="mt-0.5">
            {vestaboard.error ?? t("noBoardConfigured")}
          </Text>
        </Box>
      </Flex>
    );
  }

  if (vestaboard.mode === "cloud") {
    const cloud = vestaboard.steps.cloud_api;
    return (
      <Flex align="start" gap="2" className="p-2.5 text-xs">
        <DiagnosticStatusIcon ok={vestaboard.ok} />
        <Box className="min-w-0 flex-1">
          <Flex align="center" gap="1.5" className="font-medium">
            <Server className="h-3.5 w-3.5" />
            {t("vestaboardCloudApiLabel")}
            {cloud?.latency_ms != null && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 font-mono">
                {cloud.latency_ms}ms
              </Badge>
            )}
          </Flex>
          <Text size="xs" tone={vestaboard.ok ? "muted" : "destructive"} className="mt-0.5">
            {vestaboard.ok
              ? t("cloudApiReachable") + (cloud?.status_code ? ` (HTTP ${cloud.status_code})` : "")
              : (cloud?.error ?? (cloud?.status_code ? `HTTP ${cloud.status_code}` : t("cloudApiUnreachable")))}
          </Text>
        </Box>
      </Flex>
    );
  }

  // Local mode — show sub-steps
  const steps = vestaboard.steps;
  const stepEntries: { key: string; label: string; icon: React.ReactNode }[] = [
    { key: "dns", label: t("boardDnsLabel"), icon: <Globe className="h-3 w-3" /> },
    { key: "port", label: t("boardPortLabel"), icon: <Server className="h-3 w-3" /> },
    { key: "api", label: t("boardApiLabel"), icon: <Wifi className="h-3 w-3" /> },
  ];

  return (
    <Stack gap="1.5" className="p-2.5 text-xs">
      <Flex align="center" gap="2">
        <DiagnosticStatusIcon ok={vestaboard.ok} />
        <Flex align="center" gap="1.5" className="font-medium">
          <Server className="h-3.5 w-3.5" />
          {t("vestaboardLocalApiLabel")}
        </Flex>
      </Flex>
      <Stack gap="1" className="pl-1 border-l-2 border-muted ml-[11px]">
        {stepEntries.map(({ key, label, icon }) => {
          const step = steps[key];
          if (!step) {
            // Step wasn't reached (short-circuited)
            return (
              <Flex key={key} align="center" gap="1.5" className="pl-2 py-0.5 text-muted-foreground">
                <Box className="h-3 w-3 rounded-full border border-muted-foreground/30 flex-shrink-0" />
                {icon}
                <Text as="span" size="xs" tone="muted">
                  {label}
                </Text>
                <Text as="span" size="xs" tone="muted">
                  — {t("skipped")}
                </Text>
              </Flex>
            );
          }
          return (
            <Flex key={key} align="start" gap="1.5" className="pl-2 py-0.5">
              <DiagnosticStatusIcon ok={step.ok} />
              {icon}
              <Box className="min-w-0">
                <Text as="span" size="xs" weight="medium">
                  {label}
                </Text>
                {step.latency_ms != null && (
                  <Badge variant="secondary" className="ml-1 text-[10px] px-1 py-0 h-3.5 font-mono">
                    {step.latency_ms}ms
                  </Badge>
                )}
                {step.ok ? (
                  <Text as="span" size="xs" tone="muted" className="ml-1">
                    {key === "dns" && step.hostname ? t("hostnameResolved", { hostname: step.hostname }) : ""}
                    {key === "port" && step.port ? t("portOpen", { port: step.port }) : ""}
                    {key === "api" && step.status_code ? `HTTP ${step.status_code}` : ""}
                  </Text>
                ) : (
                  <Text as="span" size="xs" tone="destructive" className="ml-1">
                    {step.error ?? (step.status_code ? `HTTP ${step.status_code}` : t("failed"))}
                  </Text>
                )}
              </Box>
            </Flex>
          );
        })}
      </Stack>
    </Stack>
  );
}
