"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { 
  CheckCircle, 
  XCircle, 
  Loader2, 
  Wifi, 
  Cloud, 
  HelpCircle,
  Eye,
  EyeOff,
  Key,
  KeyRound,
  Search,
} from "lucide-react";
import { BoardDisplay } from "@/components/board-display";
import type { DiscoveredBoard } from "@/lib/api";

interface BoardConfig {
  api_mode: "local" | "cloud";
  local_api_key: string;
  cloud_key: string;
  host: string;
  connectionVerified: boolean;
  device_type: "flagship" | "note";
  board_color: "black" | "white";
}

interface StepBoardSetupProps {
  config: BoardConfig;
  onConfigChange: (config: BoardConfig) => void;
  onValidChange: (valid: boolean) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

type LocalKeyMode = "api_key" | "enablement_token";

export function StepBoardSetup({
  config,
  onConfigChange,
  onValidChange,
  isLoading,
  setIsLoading,
}: StepBoardSetupProps) {
  const configRef = useRef(config);
  configRef.current = config;

  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [testMessage, setTestMessage] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [localKeyMode, setLocalKeyMode] = useState<LocalKeyMode>("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [enablementStatus, setEnablementStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [enablementMessage, setEnablementMessage] = useState("");
  const [scanStatus, setScanStatus] = useState<"idle" | "scanning" | "done" | "error">("idle");
  const [discoveredBoards, setDiscoveredBoards] = useState<DiscoveredBoard[]>([]);

  // Update validity when config or test status changes
  useEffect(() => {
    const hasRequiredFields = config.api_mode === "cloud" 
      ? !!config.cloud_key
      : !!config.local_api_key && !!config.host;
    
    onValidChange(hasRequiredFields && config.connectionVerified);
  }, [config, onValidChange]);

  const handleModeChange = (mode: "local" | "cloud") => {
    onConfigChange({
      ...config,
      api_mode: mode,
      connectionVerified: false,
    });
    setTestStatus("idle");
    setTestMessage("");
    setEnablementStatus("idle");
    setEnablementMessage("");
  };

  const handleScanForBoards = async () => {
    setScanStatus("scanning");
    setDiscoveredBoards([]);
    try {
      const result = await api.scanForBoards();
      setDiscoveredBoards(result.boards);
      setScanStatus("done");
    } catch {
      setScanStatus("error");
    }
  };

  const handleSelectBoard = (board: DiscoveredBoard) => {
    onConfigChange({
      ...config,
      host: board.ip,
      connectionVerified: false,
    });
    setTestStatus("idle");
  };

  const handleEnableLocalApi = async () => {
    if (!config.host || !enablementToken) return;
    
    setEnablementStatus("loading");
    setEnablementMessage("");
    setIsLoading(true);

    try {
      const result = await api.enableLocalApi({
        host: config.host,
        enablement_token: enablementToken,
      });

      if (result.success && result.api_key) {
        setEnablementStatus("success");
        setEnablementMessage(result.message);
        // Update the config with the retrieved API key
        onConfigChange({
          ...config,
          local_api_key: result.api_key,
          connectionVerified: false,
        });
        // Switch to API key mode since we now have one
        setLocalKeyMode("api_key");
        // Clear the enablement token
        setEnablementToken("");
      } else {
        setEnablementStatus("error");
        setEnablementMessage(result.message || "Failed to enable local API");
      }
    } catch (error) {
      setEnablementStatus("error");
      setEnablementMessage(error instanceof Error ? error.message : "Failed to enable local API");
    } finally {
      setIsLoading(false);
    }
  };

  const handleTestConnection = async () => {
    setTestStatus("testing");
    setIsLoading(true);
    setTestMessage("");

    // Read the latest config from the ref to avoid stale closures
    const cfg = configRef.current;

    try {
      const result = await api.testBoardConnection({
        api_mode: cfg.api_mode,
        local_api_key: cfg.api_mode === "local" ? cfg.local_api_key : undefined,
        cloud_key: cfg.api_mode === "cloud" ? cfg.cloud_key : undefined,
        host: cfg.api_mode === "local" ? cfg.host : undefined,
      });

      if (result.success) {
        setTestStatus("success");
        setTestMessage(result.message);
        
        // Save per-board instance first (primary source of truth for settings page)
        await api.updateBoardSettings({
          boards: [{
            name: "My Board",
            device_type: cfg.device_type,
            board_color: cfg.board_color,
            api_mode: cfg.api_mode,
            host: cfg.host,
            local_api_key: cfg.local_api_key,
            cloud_key: cfg.cloud_key,
            enabled: true,
          } as import("@/lib/api").BoardInstance],
        });

        // Then save global connection config (used by validation/first-run detection)
        await api.updateBoardConfig({
          api_mode: cfg.api_mode,
          local_api_key: cfg.local_api_key,
          cloud_key: cfg.cloud_key,
          host: cfg.host,
        });
        
        onConfigChange({ ...cfg, connectionVerified: true });
      } else {
        setTestStatus("error");
        setTestMessage(result.message || "Connection failed");
        onConfigChange({ ...cfg, connectionVerified: false });
      }
    } catch (error) {
      setTestStatus("error");
      setTestMessage(error instanceof Error ? error.message : "Connection test failed");
      onConfigChange({ ...configRef.current, connectionVerified: false });
    } finally {
      setIsLoading(false);
    }
  };

  const canTest = config.api_mode === "cloud" 
    ? !!config.cloud_key
    : !!config.local_api_key && !!config.host;

  const canEnableLocalApi = !!config.host && !!enablementToken;

  const previewMessage = useMemo(() => {
    if (config.device_type === "note") {
      return [
        "   WELCOME TO  ",
        "  FIESTABOARD! ",
        "",
      ].join("\n");
    }
    const colorCodes = [64, 65, 63, 68];
    const colorRow = Array.from({ length: 22 }, (_, i) => `{${colorCodes[i % colorCodes.length]}}`).join("");
    return [
      colorRow,
      "",
      "      WELCOME TO      ",
      "     FIESTABOARD!     ",
      "",
      colorRow,
    ].join("\n");
  }, [config.device_type]);

  return (
    <div className="space-y-6">
      {/* API Mode Selection */}
      <div className="space-y-3">
        <Label className="text-base font-medium">Connection Type</Label>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => handleModeChange("cloud")}
            className={cn(
              "flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
              config.api_mode === "cloud"
                ? "border-primary bg-primary/5"
                : "border-muted hover:border-border"
            )}
          >
            <Cloud className={cn(
              "h-8 w-8",
              config.api_mode === "cloud" ? "text-primary" : "text-muted-foreground"
            )} />
            <span className="font-medium">Cloud API</span>
            <span className="text-xs text-muted-foreground text-center">
              Easiest setup
            </span>
          </button>

          <button
            type="button"
            onClick={() => handleModeChange("local")}
            className={cn(
              "flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
              config.api_mode === "local"
                ? "border-primary bg-primary/5"
                : "border-muted hover:border-border"
            )}
          >
            <Wifi className={cn(
              "h-8 w-8",
              config.api_mode === "local" ? "text-primary" : "text-muted-foreground"
            )} />
            <span className="font-medium">Local API</span>
            <span className="text-xs text-muted-foreground text-center">
              Faster, same network
            </span>
          </button>
        </div>
      </div>

      {/* Fields based on mode */}
      {config.api_mode === "cloud" ? (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="cloud_key">Read/Write API Key</Label>
            <div className="relative">
              <Input
                id="cloud_key"
                type={showApiKey ? "text" : "password"}
                placeholder="Get this from web.vestaboard.com"
                value={config.cloud_key}
                onChange={(e) => {
                  onConfigChange({
                    ...config,
                    cloud_key: e.target.value,
                    connectionVerified: false,
                  });
                  setTestStatus("idle");
                }}
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <HelpCircle className="h-3 w-3" />
              Found at web.vestaboard.com → Settings → API
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Board IP Address - always needed for local */}
          <div className="space-y-2">
            <Label htmlFor="host">Board IP Address</Label>
            <div className="flex gap-2">
              <Input
                id="host"
                placeholder="e.g., 192.168.1.100"
                value={config.host}
                onChange={(e) => {
                  onConfigChange({
                    ...config,
                    host: e.target.value,
                    connectionVerified: false,
                  });
                  setTestStatus("idle");
                  setEnablementStatus("idle");
                }}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="default"
                onClick={handleScanForBoards}
                disabled={scanStatus === "scanning"}
                title="Scan network for Vestaboards"
              >
                {scanStatus === "scanning" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <HelpCircle className="h-3 w-3" />
              Enter IP manually or click <Search className="h-3 w-3 inline" /> to scan your network
            </p>
          </div>

          {/* Scan results */}
          {scanStatus === "scanning" && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Scanning network for Vestaboards…</span>
            </div>
          )}
          {scanStatus === "done" && discoveredBoards.length === 0 && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <HelpCircle className="h-4 w-4" />
              <span>No boards found. Enter the IP address manually.</span>
            </div>
          )}
          {scanStatus === "done" && discoveredBoards.length >= 1 && (
            <div className="space-y-2">
              <Label className="text-sm">
                Found {discoveredBoards.length} {discoveredBoards.length === 1 ? "board" : "boards"} — select one:
              </Label>
              <div className="space-y-1.5">
                {discoveredBoards.map((board) => (
                  <button
                    key={board.ip}
                    type="button"
                    onClick={() => handleSelectBoard(board)}
                    className={cn(
                      "w-full flex items-center justify-between p-2.5 rounded-md border text-sm transition-colors text-left",
                      config.host === board.ip
                        ? "border-primary bg-primary/5"
                        : "border-muted hover:border-muted-foreground/30"
                    )}
                  >
                    <span className="font-mono">{board.ip}</span>
                    {board.hostname && (
                      <span className="text-xs text-muted-foreground">{board.hostname}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
          {scanStatus === "error" && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
              <XCircle className="h-4 w-4" />
              <span>Scan failed. Please enter the IP address manually.</span>
            </div>
          )}

          {/* Local Key Mode Toggle */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Authentication Method</Label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setLocalKeyMode("api_key")}
                className={cn(
                  "flex items-center justify-center gap-2 p-2.5 rounded-md border text-sm transition-all",
                  localKeyMode === "api_key"
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-muted hover:border-border text-muted-foreground"
                )}
              >
                <Key className="h-4 w-4" />
                <span>API Key</span>
              </button>
              <button
                type="button"
                onClick={() => setLocalKeyMode("enablement_token")}
                className={cn(
                  "flex items-center justify-center gap-2 p-2.5 rounded-md border text-sm transition-all",
                  localKeyMode === "enablement_token"
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-muted hover:border-border text-muted-foreground"
                )}
              >
                <KeyRound className="h-4 w-4" />
                <span>Enablement Token</span>
              </button>
            </div>
          </div>

          {localKeyMode === "api_key" ? (
            <div className="space-y-2">
              <Label htmlFor="local_api_key">Local API Key</Label>
              <div className="relative">
                <Input
                  id="local_api_key"
                  type={showApiKey ? "text" : "password"}
                  placeholder="Your local API key"
                  value={config.local_api_key}
                  onChange={(e) => {
                    onConfigChange({
                      ...config,
                      local_api_key: e.target.value,
                      connectionVerified: false,
                    });
                    setTestStatus("idle");
                  }}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <HelpCircle className="h-3 w-3" />
                Email support@vestaboard.com to request your Local API Key
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="enablement_token">Enablement Token</Label>
                <div className="relative">
                  <Input
                    id="enablement_token"
                    type={showApiKey ? "text" : "password"}
                    placeholder="Token provided by Vestaboard support"
                    value={enablementToken}
                    onChange={(e) => {
                      setEnablementToken(e.target.value);
                      setEnablementStatus("idle");
                    }}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <HelpCircle className="h-3 w-3" />
                  Email support@vestaboard.com for an enablement token
                </p>
              </div>

              <Button
                onClick={handleEnableLocalApi}
                disabled={!canEnableLocalApi || isLoading}
                variant="secondary"
                className="w-full"
              >
                {enablementStatus === "loading" ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Enabling Local API...
                  </>
                ) : enablementStatus === "success" ? (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2 text-success" />
                    API Key Retrieved!
                  </>
                ) : (
                  "Get API Key from Board"
                )}
              </Button>

              {/* Enablement status message */}
              {enablementMessage && (
                <div
                  className={cn(
                    "flex items-start gap-2 p-3 rounded-lg text-sm",
                    enablementStatus === "success" 
                      ? "bg-success/10 text-success"
                      : "bg-destructive/10 text-destructive"
                  )}
                >
                  {enablementStatus === "success" ? (
                    <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                  )}
                  <span>{enablementMessage}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Test Connection */}
      <div className="space-y-3">
        <Button
          onClick={handleTestConnection}
          disabled={!canTest || isLoading}
          variant={testStatus === "success" ? "outline" : "default"}
          className="w-full"
        >
          {testStatus === "testing" ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Testing Connection...
            </>
          ) : testStatus === "success" ? (
            <>
              <CheckCircle className="h-4 w-4 mr-2 text-success" />
              Connected! Test Again
            </>
          ) : (
            "Test Connection"
          )}
        </Button>

        {/* Status message */}
        {testMessage && (
          <div
            className={cn(
              "flex items-start gap-2 p-3 rounded-lg text-sm",
              testStatus === "success" 
                ? "bg-success/10 text-success"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {testStatus === "success" ? (
              <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            )}
            <span>{testMessage}</span>
          </div>
        )}
      </div>

      {/* Device Type & Board Color */}
      <div className="space-y-4 pt-4 border-t">
        <div className="space-y-3">
          <Label className="text-sm font-medium">Board Type</Label>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, device_type: "flagship" })}
              className={cn(
                "flex flex-col items-center gap-1.5 p-3 rounded-lg border-2 transition-all",
                config.device_type === "flagship"
                  ? "border-primary bg-primary/5"
                  : "border-muted hover:border-border"
              )}
            >
              <span className="font-medium text-sm">Flagship</span>
              <span className="text-xs text-muted-foreground">22 × 6 characters</span>
            </button>
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, device_type: "note" })}
              className={cn(
                "flex flex-col items-center gap-1.5 p-3 rounded-lg border-2 transition-all",
                config.device_type === "note"
                  ? "border-primary bg-primary/5"
                  : "border-muted hover:border-border"
              )}
            >
              <span className="font-medium text-sm">Note</span>
              <span className="text-xs text-muted-foreground">15 × 3 characters</span>
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <Label className="text-sm font-medium">Board Color</Label>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, board_color: "black" })}
              aria-label="Black"
              className={cn(
                "h-8 w-8 rounded-full border-2 bg-board-surface-dark transition-colors",
                config.board_color === "black"
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-border hover:border-muted-foreground"
              )}
            />
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, board_color: "white" })}
              aria-label="White"
              className={cn(
                "h-8 w-8 rounded-full border-2 bg-board-surface-light transition-colors",
                config.board_color === "white"
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-border hover:border-muted-foreground"
              )}
            />
          </div>
        </div>

        {/* Live board preview */}
        <div className="space-y-2 pt-3">
          <Label className="text-sm font-medium text-muted-foreground">Preview</Label>
          <BoardDisplay
            message={previewMessage}
            size="sm"
            boardType={config.board_color}
            deviceType={config.device_type}
          />
        </div>
      </div>
    </div>
  );
}
