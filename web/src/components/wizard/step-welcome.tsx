"use client";

import { Alert, AlertDescription, AlertTitle, Box, Button, Flex, Stack, Text } from "@fiestaboard/ui";
import { Clock, Puzzle } from "lucide-react";
import { useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

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
  onBack?: () => void;
  hub?: { name: string; timezone: string };
}

export function StepWelcome({
  boardConfig,
  pluginConfig,
  output,
  createdBoard,
  onComplete,
  isLoading,
  setIsLoading,
  onBack,
  hub,
}: StepWelcomeProps) {
  const otherDisplay = output && output.id !== "vestaboard" ? output : null;
  const apiMode = boardConfig.output_config.api_mode === "local" ? "local" : "cloud";
  const t = useTranslations("wizard.welcome");
  const tc = useTranslations("common");
  const tw = useTranslations("wizard");
  const [savedPlugins, setSavedPlugins] = useState<string[]>([]);
  const [saveErrors, setSaveErrors] = useState<{ id: string; message: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const busyRef = useRef(false);
  const installed = useRef(new Set(["date_time", "countdown"]));
  const busy = isLoading || saving;
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

  const enabledPlugins = [
    pluginConfig.date_time.enabled && { id: "date_time", name: t("dateTimeName"), icon: Clock },
    ...pluginConfig.registry_selected.map((id) => ({
      id,
      name: id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      icon: Puzzle,
    })),
  ].filter(Boolean) as { id: string; name: string; icon: typeof Clock }[];

  return (
    <Stack gap="4">
      <dl className="rounded-lg bg-muted p-1">
        {[
          ...(hub ? [[tw("intro.hub"), `${hub.name} · ${hub.timezone}`]] : []),
          [
            tw("review.display"),
            createdBoard?.name ??
              otherDisplay?.name ??
              (boardConfig.device_type === "flagship" ? tc("flagship") : tc("note")),
          ],
          [
            tw("review.connection"),
            otherDisplay
              ? createdBoard?.connectionVerified
                ? tw("outputSetup.verified")
                : tw("outputSetup.savedUnverified")
              : `${apiMode === "local" ? tw("connection.local") : tw("connection.cloud")} · ${boardConfig.connectionVerified ? tw("outputSetup.verified") : tw("outputSetup.savedUnverified")}`,
          ],
          [tw("review.sources"), enabledPlugins.map(({ name }) => name).join(" · ") || t("noIntegrationsSelected")],
        ].map(([label, value]) => (
          <Box key={label} className="flex flex-col gap-0.5 px-3 py-2 text-sm md:flex-row md:gap-4">
            <dt className="text-muted-foreground md:w-28 md:shrink-0">{label}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </Box>
        ))}
      </dl>
      <Text size="sm" tone="muted">
        {t("scheduleHint")}
      </Text>
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
              <Button variant="outline" disabled={busy} onClick={() => onComplete("/")}>
                {t("continueToIntegrations")}
              </Button>
            </Stack>
          </AlertDescription>
        </Alert>
      )}
      <Flex
        justify="between"
        gap="2"
        className="flex-col-reverse md:flex-row [&_button]:max-md:min-h-11 [&_button]:max-md:w-full"
      >
        {onBack && (
          <Button variant="outline" disabled={busy} onClick={onBack}>
            {tc("back")}
          </Button>
        )}
        <Button onClick={() => void handleFinish("/")} disabled={busy}>
          {saving ? t("saving") : tw("review.finish")}
        </Button>
      </Flex>
    </Stack>
  );
}
