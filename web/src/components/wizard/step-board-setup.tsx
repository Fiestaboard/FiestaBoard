"use client";

import {
  CheckCircle,
  Cloud,
  Eye,
  EyeOff,
  HelpCircle,
  Key,
  KeyRound,
  Loader2,
  Search,
  Wifi,
  XCircle,
} from "lucide-react";
import { useTranslations } from "@/i18n/translations";
import { useEffect, useMemo, useRef, useState } from "react";

import { BoardDisplay } from "@/components/board-display";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { BoardInstance, DiscoveredBoard } from "@/lib/api";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

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
  const t = useTranslations("wizard.boardSetup");
  const tc = useTranslations("common");
  const tbs = useTranslations("boardSettings");
  const configRef = useRef(config);
  configRef.current = config;

  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [testMessage, setTestMessage] = useState("");
  const [troubleshootingSteps, setTroubleshootingSteps] = useState<string[]>([]);
  const [showApiKey, setShowApiKey] = useState(false);
  const [localKeyMode, setLocalKeyMode] = useState<LocalKeyMode>("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [enablementStatus, setEnablementStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [enablementMessage, setEnablementMessage] = useState("");
  const [scanStatus, setScanStatus] = useState<"idle" | "scanning" | "done" | "error">("idle");
  const [discoveredBoards, setDiscoveredBoards] = useState<DiscoveredBoard[]>([]);

  // Update validity when config or test status changes
  useEffect(() => {
    const hasRequiredFields =
      config.api_mode === "cloud" ? !!config.cloud_key : !!config.local_api_key && !!config.host;

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
        setEnablementMessage(result.message || t("failedToEnableLocalApi"));
      }
    } catch (error) {
      setEnablementStatus("error");
      setEnablementMessage(error instanceof Error ? error.message : t("failedToEnableLocalApi"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleTestConnection = async () => {
    setTestStatus("testing");
    setIsLoading(true);
    setTestMessage("");
    setTroubleshootingSteps([]);

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
        setTroubleshootingSteps([]);

        // Save per-board instance first (primary source of truth for settings page)
        await api.updateBoardSettings({
          boards: [
            {
              name: "My Board",
              device_type: cfg.device_type,
              board_color: cfg.board_color,
              api_mode: cfg.api_mode,
              host: cfg.host,
              local_api_key: cfg.local_api_key,
              cloud_key: cfg.cloud_key,
              enabled: true,
            } as BoardInstance,
          ],
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
        setTestMessage(result.message || t("connectionTestFailed"));
        setTroubleshootingSteps(result.troubleshooting || []);
        onConfigChange({ ...cfg, connectionVerified: false });
      }
    } catch (error) {
      setTestStatus("error");
      setTestMessage(error instanceof Error ? error.message : t("connectionTestFailed"));
      setTroubleshootingSteps([]);
      onConfigChange({ ...configRef.current, connectionVerified: false });
    } finally {
      setIsLoading(false);
    }
  };

  const canTest = config.api_mode === "cloud" ? !!config.cloud_key : !!config.local_api_key && !!config.host;

  const canEnableLocalApi = !!config.host && !!enablementToken;

  const previewMessage = useMemo(() => {
    if (config.device_type === "note") {
      return ["   WELCOME TO  ", "  FIESTABOARD! ", ""].join("\n");
    }
    const colorCodes = [64, 65, 63, 68];
    const colorRow = Array.from({ length: 22 }, (_, i) => `{${colorCodes[i % colorCodes.length]}}`).join("");
    return [colorRow, "", "      WELCOME TO      ", "     FIESTABOARD!     ", "", colorRow].join("\n");
  }, [config.device_type]);

  return (
    <div className="space-y-6">
      {/* API Mode Selection */}
      <div className="space-y-3">
        <p className="text-base font-medium">{t("connectionType")}</p>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => handleModeChange("cloud")}
            className={cn(
              "flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
              config.api_mode === "cloud" ? "border-primary bg-primary/5" : "border-muted hover:border-border",
            )}
          >
            <Cloud className={cn("h-8 w-8", config.api_mode === "cloud" ? "text-primary" : "text-muted-foreground")} />
            <span className="font-medium">{t("cloudApi")}</span>
            <span className="text-xs text-muted-foreground text-center">{t("cloudApiEasiest")}</span>
          </button>

          <button
            type="button"
            onClick={() => handleModeChange("local")}
            className={cn(
              "flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
              config.api_mode === "local" ? "border-primary bg-primary/5" : "border-muted hover:border-border",
            )}
          >
            <Wifi className={cn("h-8 w-8", config.api_mode === "local" ? "text-primary" : "text-muted-foreground")} />
            <span className="font-medium">{t("localApi")}</span>
            <span className="text-xs text-muted-foreground text-center">{t("localApiFaster")}</span>
          </button>
        </div>
      </div>

      {/* Fields based on mode */}
      {config.api_mode === "cloud" ? (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="cloud_key">{t("readWriteApiKey")}</Label>
            <div className="relative">
              <Input
                id="cloud_key"
                type={showApiKey ? "text" : "password"}
                placeholder={t("cloudKeyPlaceholder")}
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
                aria-label={showApiKey ? tbs("hideApiKey") : tbs("showApiKey")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
              >
                {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <HelpCircle className="h-3 w-3" />
              {t("cloudKeyHelp")}
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Board IP Address - always needed for local */}
          <div className="space-y-2">
            <Label htmlFor="host">{t("boardIpAddress")}</Label>
            <div className="flex gap-2">
              <Input
                id="host"
                placeholder={t("boardIpPlaceholder")}
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
                title={t("scanNetworkTooltip")}
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
              {t("boardIpHelp")}
            </p>
          </div>

          {/* Scan results */}
          {scanStatus === "scanning" && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{t("scanningNetwork")}</span>
            </div>
          )}
          {scanStatus === "done" && discoveredBoards.length === 0 && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <HelpCircle className="h-4 w-4" />
              <span>{t("noBoardsFound")}</span>
            </div>
          )}
          {scanStatus === "done" && discoveredBoards.length >= 1 && (
            <div className="space-y-2">
              <p className="text-sm">{t("foundBoards", { count: discoveredBoards.length })}</p>
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
                        : "border-muted hover:border-muted-foreground/30",
                    )}
                  >
                    <span className="font-mono">{board.ip}</span>
                    {board.hostname && <span className="text-xs text-muted-foreground">{board.hostname}</span>}
                  </button>
                ))}
              </div>
            </div>
          )}
          {scanStatus === "error" && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
              <XCircle className="h-4 w-4" />
              <span>{t("scanFailed")}</span>
            </div>
          )}

          {/* Local Key Mode Toggle */}
          <div className="space-y-3">
            <p className="text-sm font-medium">{t("authenticationMethod")}</p>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setLocalKeyMode("api_key")}
                className={cn(
                  "flex items-center justify-center gap-2 p-2.5 rounded-md border text-sm transition-all",
                  localKeyMode === "api_key"
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-muted hover:border-border text-muted-foreground",
                )}
              >
                <Key className="h-4 w-4" />
                <span>{t("apiKey")}</span>
              </button>
              <button
                type="button"
                onClick={() => setLocalKeyMode("enablement_token")}
                className={cn(
                  "flex items-center justify-center gap-2 p-2.5 rounded-md border text-sm transition-all",
                  localKeyMode === "enablement_token"
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-muted hover:border-border text-muted-foreground",
                )}
              >
                <KeyRound className="h-4 w-4" />
                <span>{t("enablementToken")}</span>
              </button>
            </div>
          </div>

          {localKeyMode === "api_key" ? (
            <div className="space-y-2">
              <Label htmlFor="local_api_key">{t("localApiKey")}</Label>
              <div className="relative">
                <Input
                  id="local_api_key"
                  type={showApiKey ? "text" : "password"}
                  placeholder={t("localApiKeyPlaceholder")}
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
                  aria-label={showApiKey ? tbs("hideApiKey") : tbs("showApiKey")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <HelpCircle className="h-3 w-3" />
                {t("localApiKeyHelp")}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="enablement_token">{t("enablementToken")}</Label>
                <div className="relative">
                  <Input
                    id="enablement_token"
                    type={showApiKey ? "text" : "password"}
                    placeholder={t("enablementTokenPlaceholder")}
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
                    aria-label={showApiKey ? tbs("hideToken") : tbs("showToken")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  >
                    {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <HelpCircle className="h-3 w-3" />
                  {t("enablementTokenHelp")}
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
                    {t("enablingLocalApi")}
                  </>
                ) : enablementStatus === "success" ? (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2 text-success" />
                    {t("apiKeyRetrieved")}
                  </>
                ) : (
                  t("getApiKeyFromBoard")
                )}
              </Button>

              {/* Enablement status message */}
              {enablementMessage && (
                <div
                  className={cn(
                    "flex items-start gap-2 p-3 rounded-lg text-sm",
                    enablementStatus === "success"
                      ? "bg-success/10 text-success"
                      : "bg-destructive/10 text-destructive",
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
              {t("testingConnection")}
            </>
          ) : testStatus === "success" ? (
            <>
              <CheckCircle className="h-4 w-4 mr-2 text-success" />
              {t("connectedTestAgain")}
            </>
          ) : (
            t("testConnection")
          )}
        </Button>

        {/* Status message */}
        {testMessage && (
          <div
            className={cn(
              "flex items-start gap-2 p-3 rounded-lg text-sm",
              testStatus === "success" ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
            )}
          >
            {testStatus === "success" ? (
              <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 space-y-2">
              <span>{testMessage}</span>
              {testStatus === "error" && troubleshootingSteps.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  <p className="font-medium text-foreground/80 text-xs uppercase tracking-wide">{t("thingsToTry")}</p>
                  <ol className="list-decimal list-inside space-y-1 text-foreground/70">
                    {troubleshootingSteps.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Device Type & Board Color */}
      <div className="space-y-4 pt-4 border-t">
        <div className="space-y-3">
          <p className="text-sm font-medium">{t("boardType")}</p>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, device_type: "flagship" })}
              aria-pressed={config.device_type === "flagship"}
              className={cn(
                "flex flex-col items-center gap-1.5 p-3 rounded-lg border-2 transition-all",
                config.device_type === "flagship" ? "border-primary bg-primary/5" : "border-muted hover:border-border",
              )}
            >
              <span className="font-medium text-sm">{tc("flagship")}</span>
              <span className="text-xs text-muted-foreground">{t("flagshipDimensions")}</span>
            </button>
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, device_type: "note" })}
              aria-pressed={config.device_type === "note"}
              className={cn(
                "flex flex-col items-center gap-1.5 p-3 rounded-lg border-2 transition-all",
                config.device_type === "note" ? "border-primary bg-primary/5" : "border-muted hover:border-border",
              )}
            >
              <span className="font-medium text-sm">{tc("note")}</span>
              <span className="text-xs text-muted-foreground">{t("noteDimensions")}</span>
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <p className="text-sm font-medium">{t("boardColor")}</p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, board_color: "black" })}
              aria-label={tc("black")}
              aria-pressed={config.board_color === "black"}
              className={cn(
                "h-8 w-8 rounded-full border-2 bg-board-surface-dark transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                config.board_color === "black"
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-border hover:border-muted-foreground",
              )}
            />
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, board_color: "white" })}
              aria-label={tc("white")}
              aria-pressed={config.board_color === "white"}
              className={cn(
                "h-8 w-8 rounded-full border-2 bg-board-surface-light transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                config.board_color === "white"
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-border hover:border-muted-foreground",
              )}
            />
          </div>
        </div>

        {/* Live board preview */}
        <div className="space-y-2 pt-3">
          <p className="text-sm font-medium text-muted-foreground">{tc("preview")}</p>
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
