"use client";

import { Box, Button, DecryptedText, Flex, Heading, Stack, Text } from "@fiestaboard/ui";
import { CheckCircle, Clock, Loader2, PartyPopper, Puzzle, Send, XCircle } from "lucide-react";
import { useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

import type { WizardPluginConfig } from "./step-easy-plugins";

interface BoardConfig {
  api_mode: "local" | "cloud";
  local_api_key: string;
  cloud_key: string;
  host: string;
  connectionVerified: boolean;
  device_type: "flagship" | "note";
  board_color: "black" | "white";
}

interface StepWelcomeProps {
  boardConfig: BoardConfig;
  pluginConfig: WizardPluginConfig;
  onComplete: () => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export function StepWelcome({ boardConfig, pluginConfig, onComplete, isLoading, setIsLoading }: StepWelcomeProps) {
  const t = useTranslations("wizard.welcome");
  const tc = useTranslations("common");
  const [sendStatus, setSendStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [sendMessage, setSendMessage] = useState("");
  const [configSaved, setConfigSaved] = useState(false);

  const handleSendWelcome = async () => {
    setSendStatus("sending");
    setIsLoading(true);
    setSendMessage("");

    try {
      // Save and activate selected plugins
      if (!configSaved) {
        // Built-in: date_time
        if (pluginConfig.date_time.enabled) {
          try {
            await api.updatePluginConfig("date_time", {
              enabled: true,
              timezone: pluginConfig.date_time.timezone,
            });
            await api.enablePlugin("date_time");
          } catch (e) {
            console.warn("Failed to save date_time config:", e);
          }
        }

        // Registry plugins: install then enable each selected one
        for (const pluginId of pluginConfig.registry_selected) {
          try {
            await api.installRegistryPlugin(pluginId);
            await api.enablePlugin(pluginId);
          } catch (e) {
            console.warn(`Failed to install/enable ${pluginId}:`, e);
          }
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
        setSendMessage(t("boardInQuietHours"));
      } else {
        setSendStatus("error");
        setSendMessage(result.message || t("failedToSend"));
      }
    } catch (error) {
      setSendStatus("error");
      setSendMessage(error instanceof Error ? error.message : t("failedToSend"));
    } finally {
      setIsLoading(false);
    }
  };

  const enabledPlugins = [
    pluginConfig.date_time.enabled && { name: t("dateTimeName"), icon: Clock },
    ...pluginConfig.registry_selected.map((id) => ({
      name: id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      icon: Puzzle,
    })),
  ].filter(Boolean) as { name: string; icon: typeof Clock }[];

  return (
    <Stack gap="6">
      {/* Success header */}
      <Stack gap="2" className="text-center">
        <Flex inline align="center" justify="center" className="w-16 h-16 rounded-full bg-primary/10 mb-2">
          <PartyPopper className="h-8 w-8 text-primary" />
        </Flex>
        <Heading level={3} className="text-xl">
          <DecryptedText text={t("setupComplete")} speed={60} sequential animateOn="view" revealDirection="start" />
        </Heading>
        <Text tone="muted">{t("boardReady")}</Text>
      </Stack>

      {/* Summary */}
      <Stack gap="3" className="bg-muted/50 rounded-lg p-4">
        <Heading level={4} size="sm" className="font-medium">
          {t("summaryTitle")}
        </Heading>

        <Stack gap="2" className="text-sm">
          <Flex align="center" gap="2">
            <CheckCircle className="h-4 w-4 text-success" />
            <Text as="span">
              {boardConfig.api_mode === "local"
                ? t("boardConnectedLocal", {
                    deviceType: boardConfig.device_type === "flagship" ? tc("flagship") : tc("note"),
                    host: boardConfig.host,
                  })
                : t("boardConnected", {
                    deviceType: boardConfig.device_type === "flagship" ? tc("flagship") : tc("note"),
                    apiMode: boardConfig.api_mode === "cloud" ? "Cloud" : "Local",
                  })}
            </Text>
          </Flex>

          {enabledPlugins.length > 0 && (
            <>
              {enabledPlugins.map(({ name, icon: _Icon }) => (
                <Flex key={name} align="center" gap="2">
                  <CheckCircle className="h-4 w-4 text-success" />
                  <Text as="span">{t("pluginEnabled", { name })}</Text>
                </Flex>
              ))}
            </>
          )}

          {enabledPlugins.length === 0 && (
            <Flex align="center" gap="2" className="text-muted-foreground">
              <Text as="span" tone="muted">
                {t("noPluginsEnabled")}
              </Text>
            </Flex>
          )}
        </Stack>
      </Stack>

      {/* Send Welcome Message */}
      <Stack gap="3">
        <Box className="text-center">
          <Text tone="muted" className="mb-3">
            {t("sendWelcomeDescription")}
          </Text>

          <Button
            onClick={handleSendWelcome}
            disabled={isLoading || sendStatus === "success"}
            size="lg"
            className={cn("w-full transition-all", sendStatus === "success" && "bg-success hover:bg-success/90")}
          >
            {sendStatus === "sending" ? (
              <>
                <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                {tc("sending")}
              </>
            ) : sendStatus === "success" ? (
              <>
                <CheckCircle className="h-5 w-5 mr-2" />
                {t("messageSent")}
              </>
            ) : (
              <>
                <Send className="h-5 w-5 mr-2" />
                {t("sendHelloButton")}
              </>
            )}
          </Button>
        </Box>

        {/* Status message */}
        {sendMessage && (
          <Flex
            align="start"
            gap="2"
            className={cn(
              "p-3 rounded-lg text-sm",
              sendStatus === "success" ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
            )}
          >
            {sendStatus === "success" ? (
              <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            )}
            {sendMessage}
          </Flex>
        )}
      </Stack>

      {/* Complete button */}
      <Box className="pt-4">
        <Button
          onClick={onComplete}
          variant={sendStatus === "success" ? "default" : "outline"}
          className="w-full"
          size="lg"
        >
          {sendStatus === "success" ? t("goToDashboard") : t("skipGoToDashboard")}
        </Button>
      </Box>
    </Stack>
  );
}
