"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Monitor, Eye, EyeOff, AlertCircle, Check, Key, KeyRound, Loader2, Search } from "lucide-react";
import { api, BoardConfig } from "@/lib/api";
import type { DiscoveredBoard } from "@/lib/api";

type LocalKeyMode = "api_key" | "enablement_token";

export function BoardSettings() {
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<Partial<BoardConfig>>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [localKeyMode, setLocalKeyMode] = useState<LocalKeyMode>("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [isEnabling, setIsEnabling] = useState(false);
  const [scanStatus, setScanStatus] = useState<"idle" | "scanning" | "done" | "error">("idle");
  const [discoveredBoards, setDiscoveredBoards] = useState<DiscoveredBoard[]>([]);

  // Fetch current config
  const { data: configData, isLoading } = useQuery({
    queryKey: ["board-config"],
    queryFn: api.getBoardConfig,
  });

  // Initialize form
  useEffect(() => {
    if (configData?.config) {
      setFormData(configData.config);
      setHasChanges(false);
    }
  }, [configData]);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: Partial<BoardConfig>) =>
      api.updateBoardConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-config"] });
      queryClient.invalidateQueries({ queryKey: ["config"] });
      queryClient.invalidateQueries({ queryKey: ["status"] });
      toast.success("Board settings saved");
      setHasChanges(false);
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // Handle field change
  const handleChange = (key: keyof BoardConfig, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  // Handle save
  const handleSave = () => {
    updateMutation.mutate(formData);
  };

  // Handle enablement token exchange
  const handleEnableLocalApi = async () => {
    if (!formData.host || !enablementToken) {
      toast.error("Board host and enablement token are required");
      return;
    }

    setIsEnabling(true);
    try {
      const result = await api.enableLocalApi({
        host: formData.host,
        enablement_token: enablementToken,
      });

      if (result.success && result.api_key) {
        // Update the form with the retrieved API key
        handleChange("local_api_key", result.api_key);
        setEnablementToken("");
        setLocalKeyMode("api_key");
        toast.success("Local API enabled! API key retrieved and saved.");
      } else {
        toast.error(result.message || "Failed to enable local API");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to enable local API");
    } finally {
      setIsEnabling(false);
    }
  };

  // Handle scanning for boards on the network
  const handleScanForBoards = async () => {
    setScanStatus("scanning");
    setDiscoveredBoards([]);
    try {
      const result = await api.scanForBoards();
      setDiscoveredBoards(result.boards);
      setScanStatus("done");
      if (result.boards.length >= 1) {
        toast.info(`Found ${result.boards.length} ${result.boards.length === 1 ? "board" : "boards"} on your network`);
      } else {
        toast.info("No boards found on your network");
      }
    } catch {
      setScanStatus("error");
      toast.error("Network scan failed");
    }
  };

  // Auto-save when form data changes (debounced)
  useEffect(() => {
    // Skip if no changes or if a mutation is already in progress
    if (!hasChanges || updateMutation.isPending) {
      return;
    }

    // Debounce auto-save by 1 second
    const timeoutId = setTimeout(() => {
      handleSave();
    }, 1000);

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData, hasChanges]);

  const apiMode = formData.api_mode ?? "local";
  const hasLocalKey = formData.local_api_key === "***" || (formData.local_api_key && formData.local_api_key.length > 0);
  const hasCloudKey = formData.cloud_key === "***" || (formData.cloud_key && formData.cloud_key.length > 0);
  const hasHost = formData.host && formData.host.length > 0;

  const isConfigValid =
    (apiMode === "local" && hasLocalKey && hasHost) ||
    (apiMode === "cloud" && hasCloudKey);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-40 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-md bg-primary/10">
              <Monitor className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                Board Connection
                {isConfigValid ? (
                  <Badge variant="default" className="text-xs bg-board-green">
                    <Check className="h-3 w-3 mr-1" />
                    Configured
                  </Badge>
                ) : (
                  <Badge variant="destructive" className="text-xs">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    Incomplete
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Configure how to connect to your board
              </CardDescription>
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <TooltipProvider>
        {/* API Mode */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium">Connection Mode</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => handleChange("api_mode", "local")}
              className={`p-3 rounded-md border text-left transition-colors ${
                apiMode === "local"
                  ? "border-primary bg-primary/10"
                  : "border-muted hover:border-primary/50"
              }`}
            >
              <div className="text-sm font-medium">Local API</div>
              <div className="text-xs text-muted-foreground">
                Direct connection (faster)
              </div>
            </button>
            <button
              onClick={() => handleChange("api_mode", "cloud")}
              className={`p-3 rounded-md border text-left transition-colors ${
                apiMode === "cloud"
                  ? "border-primary bg-primary/10"
                  : "border-muted hover:border-primary/50"
              }`}
            >
              <div className="text-sm font-medium">Cloud API</div>
              <div className="text-xs text-muted-foreground">
                Via cloud servers
              </div>
            </button>
          </div>
        </div>

        {/* Local API Fields */}
        {apiMode === "local" && (
          <>
            {/* Board Host - always needed for local */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium">
                Board Host <span className="text-destructive">*</span>
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={formData.host ?? ""}
                  onChange={(e) => handleChange("host", e.target.value)}
                  placeholder="192.168.1.100"
                  className="flex-1 h-9 px-3 text-sm rounded-md border bg-background font-mono"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleScanForBoards}
                  disabled={scanStatus === "scanning"}
                  className="h-9 w-9 p-0"
                  title="Scan network for boards"
                >
                  {scanStatus === "scanning" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Search className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                IP address or hostname of your board
              </p>
            </div>

            {/* Scan results */}
            {scanStatus === "done" && discoveredBoards.length >= 1 && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium">
                  Found {discoveredBoards.length} {discoveredBoards.length === 1 ? "board" : "boards"} — select one:
                </label>
                <div className="space-y-1">
                  {discoveredBoards.map((board) => (
                    <button
                      key={board.ip}
                      type="button"
                      onClick={() => {
                        handleChange("host", board.ip);
                      }}
                      className={`w-full flex items-center justify-between p-2 rounded-md border text-xs transition-colors text-left ${
                        formData.host === board.ip
                          ? "border-primary bg-primary/10"
                          : "border-muted hover:border-primary/50"
                      }`}
                    >
                      <span className="font-mono">{board.ip}</span>
                      {board.hostname && (
                        <span className="text-muted-foreground">{board.hostname}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Local Key Mode Toggle */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Authentication Method</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setLocalKeyMode("api_key")}
                  className={`flex items-center justify-center gap-1.5 p-2 rounded-md border text-xs transition-colors ${
                    localKeyMode === "api_key"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-muted hover:border-primary/50 text-muted-foreground"
                  }`}
                >
                  <Key className="h-3.5 w-3.5" />
                  <span>API Key</span>
                </button>
                <button
                  type="button"
                  onClick={() => setLocalKeyMode("enablement_token")}
                  className={`flex items-center justify-center gap-1.5 p-2 rounded-md border text-xs transition-colors ${
                    localKeyMode === "enablement_token"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-muted hover:border-primary/50 text-muted-foreground"
                  }`}
                >
                  <KeyRound className="h-3.5 w-3.5" />
                  <span>Enablement Token</span>
                </button>
              </div>
            </div>

            {localKeyMode === "api_key" ? (
              <div className="space-y-1.5">
                <label className="text-xs font-medium">
                  Local API Key <span className="text-destructive">*</span>
                </label>
                <div className="flex gap-2">
                  <input
                    type={showSecrets.local_api_key ? "text" : "password"}
                    value={
                      formData.local_api_key === "***"
                        ? ""
                        : (formData.local_api_key ?? "")
                    }
                    onChange={(e) => handleChange("local_api_key", e.target.value)}
                    placeholder={hasLocalKey ? "••••••••••• (value set)" : "Enter your local API key"}
                    className="flex-1 h-9 px-3 text-sm rounded-md border bg-background font-mono"
                  />
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label={showSecrets.local_api_key ? "Hide API key" : "Show API key"}
                        onClick={() =>
                          setShowSecrets((prev) => ({
                            ...prev,
                            local_api_key: !prev.local_api_key,
                          }))
                        }
                        className="h-9 w-9 p-0"
                        disabled={formData.local_api_key === "***"}
                      >
                        {showSecrets.local_api_key ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>{formData.local_api_key === "***" ? "Cannot reveal server-stored values" : "Toggle visibility"}</p>
                    </TooltipContent>
                  </Tooltip>
                </div>
                <p className="text-xs text-muted-foreground">
                  See our{" "}
                  <a href="https://fiestaboard.app/docs/setup/api-keys" target="_blank" rel="noopener noreferrer" className="underline">setup guide</a>
                  {" "}for how to get your Local API key
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium">
                    Enablement Token
                  </label>
                  <div className="flex gap-2">
                    <input
                      type={showSecrets.enablement_token ? "text" : "password"}
                      value={enablementToken}
                      onChange={(e) => setEnablementToken(e.target.value)}
                      placeholder="Token from vestaboard.com/local-api"
                      className="flex-1 h-9 px-3 text-sm rounded-md border bg-background font-mono"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-label={showSecrets.enablement_token ? "Hide token" : "Show token"}
                      onClick={() =>
                        setShowSecrets((prev) => ({
                          ...prev,
                          enablement_token: !prev.enablement_token,
                        }))
                      }
                      className="h-9 w-9 p-0"
                    >
                      {showSecrets.enablement_token ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Request an enablement token at{" "}
                    <a href="https://www.vestaboard.com/local-api" target="_blank" rel="noopener noreferrer" className="underline">vestaboard.com/local-api</a>
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleEnableLocalApi}
                  disabled={!formData.host || !enablementToken || isEnabling}
                  className="w-full"
                >
                  {isEnabling ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      Enabling...
                    </>
                  ) : (
                    "Get API Key from Board"
                  )}
                </Button>
              </div>
            )}
          </>
        )}

        {/* Cloud API Fields */}
        {apiMode === "cloud" && (
          <div className="space-y-1.5">
            <label className="text-xs font-medium">
              Read/Write API Key <span className="text-destructive">*</span>
            </label>
            <div className="flex gap-2">
              <input
                type={showSecrets.cloud_key ? "text" : "password"}
                value={
                  formData.cloud_key === "***"
                    ? ""
                    : (formData.cloud_key ?? "")
                }
                onChange={(e) => handleChange("cloud_key", e.target.value)}
                placeholder={hasCloudKey ? "••••••••••• (value set)" : "Enter your R/W API key"}
                className="flex-1 h-9 px-3 text-sm rounded-md border bg-background font-mono"
              />
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    aria-label={showSecrets.cloud_key ? "Hide cloud key" : "Show cloud key"}
                    onClick={() =>
                      setShowSecrets((prev) => ({
                        ...prev,
                        cloud_key: !prev.cloud_key,
                      }))
                    }
                    className="h-9 w-9 p-0"
                    disabled={formData.cloud_key === "***"}
                  >
                    {showSecrets.cloud_key ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{formData.cloud_key === "***" ? "Cannot reveal server-stored values" : "Toggle visibility"}</p>
                </TooltipContent>
              </Tooltip>
            </div>
            <p className="text-xs text-muted-foreground">
              Found in the Vestaboard app under Settings → Read/Write API
            </p>
          </div>
        )}

        {/* Validation message */}
        {!isConfigValid && (
          <div className="flex items-center gap-2 p-2 rounded-md bg-destructive/10 text-foreground text-xs">
            <AlertCircle className="h-4 w-4" />
            <span>
              {apiMode === "local"
                ? "Local API key and host are required"
                : "Cloud API key is required"}
            </span>
          </div>
        )}

        {/* Auto-save indicator */}
        {updateMutation.isPending && (
          <div className="flex items-center justify-center gap-2 pt-2 text-xs text-muted-foreground">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span>Saving...</span>
          </div>
        )}
        </TooltipProvider>
      </CardContent>
    </Card>
  );
}

// Backward compatibility alias
export const FiestaboardSettings = BoardSettings;

