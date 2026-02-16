"use client";

import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
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
  Monitor,
  Smartphone
} from "lucide-react";

interface BoardConfig {
  api_mode: "local" | "cloud";
  local_api_key: string;
  cloud_key: string;
  host: string;
  connectionVerified: boolean;
  devices: string[];
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
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [testMessage, setTestMessage] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [localKeyMode, setLocalKeyMode] = useState<LocalKeyMode>("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [enablementStatus, setEnablementStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [enablementMessage, setEnablementMessage] = useState("");

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

    try {
      const result = await api.testBoardConnection({
        api_mode: config.api_mode,
        local_api_key: config.api_mode === "local" ? config.local_api_key : undefined,
        cloud_key: config.api_mode === "cloud" ? config.cloud_key : undefined,
        host: config.api_mode === "local" ? config.host : undefined,
      });

      if (result.success) {
        setTestStatus("success");
        setTestMessage(result.message);
        
        // Save the config to the server
        await api.updateBoardConfig({
          api_mode: config.api_mode,
          local_api_key: config.local_api_key,
          cloud_key: config.cloud_key,
          host: config.host,
        });
        
        onConfigChange({ ...config, connectionVerified: true });
      } else {
        setTestStatus("error");
        setTestMessage(result.message || "Connection failed");
        onConfigChange({ ...config, connectionVerified: false });
      }
    } catch (error) {
      setTestStatus("error");
      setTestMessage(error instanceof Error ? error.message : "Connection test failed");
      onConfigChange({ ...config, connectionVerified: false });
    } finally {
      setIsLoading(false);
    }
  };

  const canTest = config.api_mode === "cloud" 
    ? !!config.cloud_key
    : !!config.local_api_key && !!config.host;

  const canEnableLocalApi = !!config.host && !!enablementToken;

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
                : "border-muted hover:border-muted-foreground/30"
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
                : "border-muted hover:border-muted-foreground/30"
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
            />
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <HelpCircle className="h-3 w-3" />
              Your board&apos;s local IP address (found in Board App → Settings)
            </p>
          </div>

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
                    : "border-muted hover:border-muted-foreground/30 text-muted-foreground"
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
                    : "border-muted hover:border-muted-foreground/30 text-muted-foreground"
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
                    <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
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
                      ? "bg-green-500/10 text-green-700 dark:text-green-400"
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
              <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
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
                ? "bg-green-500/10 text-green-700 dark:text-green-400"
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

      {/* Device & Board Color Selection */}
      <div className="space-y-4 pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Your Devices</Label>
          <p className="text-xs text-muted-foreground mt-1">
            Select which Vestaboard devices you own
          </p>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Monitor className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Flagship</span>
              <span className="text-xs text-muted-foreground">22×6</span>
            </div>
            <Switch
              checked={config.devices.includes("flagship")}
              onCheckedChange={(checked) => {
                const devices = checked
                  ? [...config.devices, "flagship"]
                  : config.devices.filter(d => d !== "flagship");
                if (devices.length === 0) return;
                onConfigChange({ ...config, devices });
              }}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Smartphone className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Note</span>
              <span className="text-xs text-muted-foreground">15×3</span>
            </div>
            <Switch
              checked={config.devices.includes("note")}
              onCheckedChange={(checked) => {
                const devices = checked
                  ? [...config.devices, "note"]
                  : config.devices.filter(d => d !== "note");
                if (devices.length === 0) return;
                onConfigChange({ ...config, devices });
              }}
            />
          </div>
        </div>
        <div className="pt-2">
          <Label className="text-sm font-medium">Board Color</Label>
          <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-2">
              <div
                className="h-4 w-4 rounded border"
                style={{ backgroundColor: config.board_color === "white" ? "#fafafa" : "#0d0d0d" }}
              />
              <span className="text-sm">
                {config.board_color === "white" ? "White" : "Black"}
              </span>
            </div>
            <Switch
              checked={config.board_color === "white"}
              onCheckedChange={(checked) => {
                onConfigChange({ ...config, board_color: checked ? "white" : "black" });
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
