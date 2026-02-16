"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { 
  PartyPopper, 
  CheckCircle, 
  XCircle, 
  Loader2, 
  Send,
  Clock,
  Star,
  Wifi
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

interface PluginConfig {
  date_time: { enabled: boolean; timezone: string };
  star_trek_quotes: { enabled: boolean; ratio: string };
  guest_wifi: { enabled: boolean; ssid: string; password: string };
}

interface StepWelcomeProps {
  boardConfig: BoardConfig;
  pluginConfig: PluginConfig;
  onComplete: () => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export function StepWelcome({
  boardConfig,
  pluginConfig,
  onComplete,
  isLoading,
  setIsLoading,
}: StepWelcomeProps) {
  const [sendStatus, setSendStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [sendMessage, setSendMessage] = useState("");
  const [configSaved, setConfigSaved] = useState(false);

  const handleSendWelcome = async () => {
    setSendStatus("sending");
    setIsLoading(true);
    setSendMessage("");

    try {
      // First, save all the plugin configurations
      if (!configSaved) {
        // Save date_time config
        if (pluginConfig.date_time.enabled) {
          try {
            await api.updatePluginConfig("date_time", {
              enabled: true,
              timezone: pluginConfig.date_time.timezone,
            });
          } catch (e) {
            console.warn("Failed to save date_time config:", e);
          }
        }

        // Save star_trek_quotes config
        if (pluginConfig.star_trek_quotes.enabled) {
          try {
            await api.updatePluginConfig("star_trek_quotes", {
              enabled: true,
              ratio: pluginConfig.star_trek_quotes.ratio,
            });
          } catch (e) {
            console.warn("Failed to save star_trek_quotes config:", e);
          }
        }

        // Save guest_wifi config
        if (pluginConfig.guest_wifi.enabled && pluginConfig.guest_wifi.ssid) {
          try {
            await api.updatePluginConfig("guest_wifi", {
              enabled: true,
              ssid: pluginConfig.guest_wifi.ssid,
              password: pluginConfig.guest_wifi.password,
            });
          } catch (e) {
            console.warn("Failed to save guest_wifi config:", e);
          }
        }

        // Save board display settings (devices & color)
        try {
          await api.updateBoardSettings({
            devices: boardConfig.devices as import("@/lib/api").DeviceType[],
            board_type: boardConfig.board_color,
          });
        } catch (e) {
          console.warn("Failed to save board display settings:", e);
        }

        setConfigSaved(true);
      }

      // Send the welcome message
      const result = await api.sendWelcomeMessage();

      if (result.status === "success") {
        setSendStatus("success");
        setSendMessage(result.message);
      } else if (result.status === "blocked") {
        setSendStatus("success");
        setSendMessage("Board is in quiet hours - message queued for later!");
      } else {
        setSendStatus("error");
        setSendMessage(result.message || "Failed to send");
      }
    } catch (error) {
      setSendStatus("error");
      setSendMessage(error instanceof Error ? error.message : "Failed to send welcome message");
    } finally {
      setIsLoading(false);
    }
  };

  const enabledPlugins = [
    pluginConfig.date_time.enabled && { name: "Date & Time", icon: Clock },
    pluginConfig.star_trek_quotes.enabled && { name: "Star Trek Quotes", icon: Star },
    pluginConfig.guest_wifi.enabled && pluginConfig.guest_wifi.ssid && { name: "Guest WiFi", icon: Wifi },
  ].filter(Boolean) as { name: string; icon: typeof Clock }[];

  return (
    <div className="space-y-6">
      {/* Success header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-2">
          <PartyPopper className="h-8 w-8 text-primary" />
        </div>
        <h3 className="text-xl font-semibold">Setup Complete!</h3>
        <p className="text-muted-foreground">
          Your FiestaBoard is ready to shine
        </p>
      </div>

      {/* Summary */}
      <div className="space-y-3 bg-muted/50 rounded-lg p-4">
        <h4 className="font-medium text-sm">What you've set up:</h4>
        
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span>
              Board connected via {boardConfig.api_mode === "cloud" ? "Cloud" : "Local"} API
              {boardConfig.api_mode === "local" && ` (${boardConfig.host})`}
            </span>
          </div>

          {enabledPlugins.length > 0 && (
            <>
              {enabledPlugins.map(({ name, icon: Icon }) => (
                <div key={name} className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>{name} enabled</span>
                </div>
              ))}
            </>
          )}

          {enabledPlugins.length === 0 && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <span>No additional features enabled (you can add them later in Settings)</span>
            </div>
          )}
        </div>
      </div>

      {/* Send Welcome Message */}
      <div className="space-y-3">
        <div className="text-center">
          <p className="text-sm text-muted-foreground mb-3">
            Let's send a colorful welcome message to your board!
          </p>
          
          <Button
            onClick={handleSendWelcome}
            disabled={isLoading || sendStatus === "success"}
            size="lg"
            className={cn(
              "w-full transition-all",
              sendStatus === "success" && "bg-green-500 hover:bg-green-600"
            )}
          >
            {sendStatus === "sending" ? (
              <>
                <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                Sending...
              </>
            ) : sendStatus === "success" ? (
              <>
                <CheckCircle className="h-5 w-5 mr-2" />
                Message Sent!
              </>
            ) : (
              <>
                <Send className="h-5 w-5 mr-2" />
                Send "Hello from FiestaBoard"
              </>
            )}
          </Button>
        </div>

        {/* Status message */}
        {sendMessage && (
          <div
            className={cn(
              "flex items-start gap-2 p-3 rounded-lg text-sm",
              sendStatus === "success" 
                ? "bg-green-500/10 text-green-700 dark:text-green-400"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {sendStatus === "success" ? (
              <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            )}
            <span>{sendMessage}</span>
          </div>
        )}
      </div>

      {/* Complete button */}
      <div className="pt-4">
        <Button
          onClick={onComplete}
          variant={sendStatus === "success" ? "default" : "outline"}
          className="w-full"
          size="lg"
        >
          {sendStatus === "success" ? "Go to Dashboard" : "Skip & Go to Dashboard"}
        </Button>
      </div>
    </div>
  );
}

