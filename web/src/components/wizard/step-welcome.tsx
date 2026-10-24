"use client";

import { Alert, AlertDescription, AlertTitle, Box, Button, Flex, Heading, Stack, Text } from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { CheckCircle, Clock, Info, PartyPopper, Puzzle, Send, XCircle } from "lucide-react";
import { useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import type { BoardConfig } from "./step-board-setup";
import type { WizardPluginConfig } from "./step-easy-plugins";
import type { WizardCreatedBoard, WizardOutputChoice } from "./step-output-plugin";

interface StepWelcomeProps {
  boardConfig: BoardConfig;
  pluginConfig: WizardPluginConfig;
  /** The display chosen on the first step; null or Vestaboard → the Vestaboard summary. */
  output?: WizardOutputChoice | null;
  /** The board a TV or output-plugin step created. */
  createdBoard?: WizardCreatedBoard | null;
  onComplete: (destination?: "/" | "/pages/new" | "/integrations") => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export function StepWelcome({
  boardConfig,
  pluginConfig,
  output,
  createdBoard,
  onComplete,
  isLoading,
  setIsLoading,
}: StepWelcomeProps) {
  const otherDisplay = output && output.id !== "vestaboard" ? output : null;
  const apiMode = boardConfig.output_config.api_mode === "local" ? "local" : "cloud";
  const t = useTranslations("wizard.welcome");
  const tc = useTranslations("common");
  const [sendStatus, setSendStatus] = useState<"idle" | "sending" | "success" | "blocked" | "error">("idle");
  const [sendMessage, setSendMessage] = useState("");
  const [savedPlugins, setSavedPlugins] = useState<string[]>([]);
  const [saveErrors, setSaveErrors] = useState<{ id: string; message: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const busyRef = useRef(false);
  const installed = useRef(new Set(["date_time", "countdown"]));
  const busy = isLoading || saving || sendStatus === "sending";
  const pluginName = (id: string) =>
    id === "date_time" ? t("dateTimeName") : id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const handleFinish = async (destination: "/" | "/pages/new") => {
    if (busyRef.current || busy) return;
    busyRef.current = true;
    setSaving(true);
    setIsLoading(true);
    setSaveErrors([]);
    const errors: { id: string; message: string }[] = [];
    const selected = [...(pluginConfig.date_time.enabled ? ["date_time"] : []), ...pluginConfig.registry_selected];
    try {
      // Never reinstall an integration that already exists on this server.
      if (selected.some((id) => !installed.current.has(id) && !savedPlugins.includes(id))) {
        const { plugins } = await api.listPlugins();
        plugins.forEach((plugin) => installed.current.add(plugin.id));
      }
      for (const id of new Set(selected)) {
        if (savedPlugins.includes(id)) continue;
        try {
          if (!installed.current.has(id)) {
            await api.installRegistryPlugin(id);
            installed.current.add(id);
          }
          if (id === "date_time") {
            await api.updatePluginConfig(id, { timezone: pluginConfig.date_time.timezone });
          }
          await api.enablePlugin(id);
          setSavedPlugins((previous) => [...previous, id]);
        } catch (error) {
          errors.push({ id, message: error instanceof Error ? error.message : t("saveFailed") });
        }
      }
      setSaveErrors(errors);
      if (errors.length === 0) onComplete(destination);
    } catch (error) {
      setSaveErrors([{ id: "", message: error instanceof Error ? error.message : t("saveFailed") }]);
    } finally {
      busyRef.current = false;
      setSaving(false);
      setIsLoading(false);
    }
  };

  const handleSendWelcome = async () => {
    if (busyRef.current || busy) return;
    busyRef.current = true;
    setSendStatus("sending");
    setIsLoading(true);
    setSendMessage("");

    try {
      // Send the welcome message to the display this wizard set up: a board
      // the TV or output-plugin step created is named, since a seeded
      // placeholder Vestaboard may still be the primary. The Vestaboard path
      // configured the primary itself.
      const result =
        otherDisplay && createdBoard
          ? await api.sendWelcomeMessage(createdBoard.boardId)
          : await api.sendWelcomeMessage();
      setSendStatus("success");
      setSendMessage(result.message);
    } catch (error) {
      // A refused send is not queued. Keep setup available and allow a retry.
      if (error instanceof ApiError && error.status === 409) {
        setSendStatus("blocked");
        setSendMessage(t("messageBlocked"));
        return;
      }
      setSendStatus("error");
      setSendMessage(error instanceof Error ? error.message : t("failedToSend"));
    } finally {
      busyRef.current = false;
      setIsLoading(false);
    }
  };

  const enabledPlugins = [
    pluginConfig.date_time.enabled && { id: "date_time", name: t("dateTimeName"), icon: Clock },
    ...pluginConfig.registry_selected.map((id) => ({
      id,
      name: id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      icon: Puzzle,
    })),
  ].filter(Boolean) as { id: string; name: string; icon: typeof Clock }[];

  return (
    <Stack gap="6">
      {/* Success header */}
      <Stack gap="2" className="text-center">
        <Flex inline align="center" justify="center" className="w-16 h-16 rounded-full bg-primary/10 mb-2">
          <PartyPopper className="h-8 w-8 text-primary" />
        </Flex>
        <Heading level={3} className="text-xl">
          {t("reviewTitle")}
        </Heading>
        <Text tone="muted">{t("reviewDescription")}</Text>
      </Stack>

      {/* Summary */}
      <Stack gap="3" className="bg-muted/50 rounded-lg p-4">
        <Heading level={4} size="sm" className="font-medium">
          {t("reviewSummary")}
        </Heading>

        <Stack gap="2" className="text-sm">
          <Flex align="center" gap="2">
            <CheckCircle className="h-4 w-4 text-success" />
            <Text as="span">
              {otherDisplay
                ? t("displayReady", { name: createdBoard?.name ?? otherDisplay.name, output: otherDisplay.name })
                : apiMode === "local"
                  ? t("boardConnectedLocal", {
                      deviceType: boardConfig.device_type === "flagship" ? tc("flagship") : tc("note"),
                      host: String(boardConfig.output_config.host ?? ""),
                    })
                  : t("boardConnected", {
                      deviceType: boardConfig.device_type === "flagship" ? tc("flagship") : tc("note"),
                      apiMode: apiMode === "cloud" ? "Cloud" : "Local",
                    })}
            </Text>
          </Flex>

          {enabledPlugins.length > 0 && (
            <>
              {enabledPlugins.map(({ id, name }) => (
                <Flex key={name} align="center" gap="2">
                  {savedPlugins.includes(id) ? (
                    <CheckCircle className="h-4 w-4 text-success" />
                  ) : (
                    <Puzzle className="h-4 w-4 text-muted-foreground" />
                  )}
                  <Text as="span">{t(savedPlugins.includes(id) ? "pluginEnabled" : "pluginSelected", { name })}</Text>
                </Flex>
              ))}
            </>
          )}

          {enabledPlugins.length === 0 && (
            <Flex align="center" gap="2" className="text-muted-foreground">
              <Text as="span" tone="muted">
                {t("noIntegrationsSelected")}
              </Text>
            </Flex>
          )}
        </Stack>
      </Stack>

      {/* Send Welcome Message */}
      <Stack gap="3">
        <Box className="text-center">
          <Text tone="muted" className="mb-3">
            {t("optionalTestDescription")}
          </Text>

          <Button
            onClick={handleSendWelcome}
            disabled={busy || sendStatus === "success"}
            size="lg"
            className={cn("w-full transition-all", sendStatus === "success" && "bg-success hover:bg-success/90")}
          >
            {sendStatus === "sending" ? (
              <>
                <Spinner label={null} className="h-5 w-5 mr-2" />
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
            role={sendStatus === "error" ? "alert" : "status"}
            className={cn(
              "p-3 rounded-lg text-sm",
              sendStatus === "success"
                ? "bg-success/10 text-success"
                : sendStatus === "blocked"
                  ? "bg-muted text-foreground"
                  : "bg-destructive/10 text-destructive",
            )}
          >
            {sendStatus === "success" ? (
              <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            ) : sendStatus === "blocked" ? (
              <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            )}
            {sendMessage}
          </Flex>
        )}
      </Stack>

      <Stack gap="2" className="rounded-lg border p-4">
        <Heading level={4} size="sm">
          {t("nextTitle")}
        </Heading>
        <Text size="sm" tone="muted">
          {t("nextDescription")}
        </Text>
        <Text size="sm" tone="muted">
          {t("scheduleHint")}
        </Text>
      </Stack>

      {saveErrors.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>{t("saveFailed")}</AlertTitle>
          <AlertDescription>
            <Stack gap="2">
              {saveErrors.map(({ id, message }) => (
                <Text key={id} size="sm">
                  {id ? `${pluginName(id)}: ${message}` : message}
                </Text>
              ))}
              <Text size="sm">{t("saveRetryHint")}</Text>
              <Button variant="outline" disabled={busy} onClick={() => onComplete("/integrations")}>
                {t("continueToIntegrations")}
              </Button>
            </Stack>
          </AlertDescription>
        </Alert>
      )}

      <Stack gap="2" className="pt-4">
        {saving && (
          <Text role="status" size="sm">
            {t("saving")}
          </Text>
        )}
        <Button onClick={() => void handleFinish("/pages/new")} disabled={busy} className="w-full" size="lg">
          {t("createFirstPage")}
        </Button>
        <Button onClick={() => void handleFinish("/")} disabled={busy} variant="outline" className="w-full" size="lg">
          {t("saveGoToDashboard")}
        </Button>
      </Stack>
    </Stack>
  );
}
