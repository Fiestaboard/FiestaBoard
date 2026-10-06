"use client";

/**
 * The install's plugin settings, as one row in the Integrations page header:
 * the auto-update switch, a "Check for updates" button, and the switch that
 * lets third-party output plugins (displays from the marketplace or a git
 * URL) drive boards. Auto-update used to be a Settings card ("Plugin
 * Updates") and the output switch lived under Settings → Advanced → Beta
 * until settings v6; both live beside the plugins they act on now.
 *
 * The `settings.plugins` anchors stay on it, so the AI walkthrough for
 * `update_setting(category="plugins")` still has something to point at.
 */

import { Button, Flex, Label, Switch } from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { usePluginSettings, useUpdatePluginSettings } from "@/hooks/use-plugin-settings";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const AUTO_UPDATE_SWITCH_ID = "plugin-auto-update";
const OUTPUT_PLUGINS_SWITCH_ID = "plugin-output-plugins";

export function PluginUpdatesControl() {
  const t = useTranslations("integrations");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const { data: settings } = usePluginSettings();

  const settingsMutation = useUpdatePluginSettings({
    onSuccess: () => {
      toast.success(t("autoUpdateSavedToast"));
    },
    onError: (err: Error) => {
      toast.error(t("autoUpdateSaveFailedToast", { error: err.message }));
    },
  });

  const checkMutation = useMutation({
    mutationFn: () => api.triggerPluginUpdateCheck(),
    onSuccess: (result) => {
      const count = result.updates_available.length;
      toast.success(count > 0 ? t("toastUpdatesFound", { count }) : t("toastNoUpdates"));
    },
    onError: (err: unknown) => {
      toast.error(t("toastCheckFailed", { error: err instanceof Error ? err.message : tCommon("error") }));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-updates"] });
    },
  });

  return (
    <Flex align="center" gap="4" wrap className="justify-start sm:justify-end" {...anchorProps("settings.plugins")}>
      {/* Hidden until the settings have loaded: a switch drawn "off" while the
          request is in flight reads as a fact and invites a click that would
          save the wrong value. */}
      {settings && (
        <Flex align="center" gap="2">
          <Switch
            id={AUTO_UPDATE_SWITCH_ID}
            checked={settings.auto_update}
            disabled={settingsMutation.isPending}
            onCheckedChange={(checked) => settingsMutation.mutate({ auto_update: checked })}
            {...anchorProps("settings.plugins.auto_update")}
          />
          <Label htmlFor={AUTO_UPDATE_SWITCH_ID} className="text-sm font-normal">
            {t("autoUpdateLabel")}
          </Label>
        </Flex>
      )}
      {settings && (
        <Flex align="center" gap="2" title={t("outputPluginsDescription")}>
          <Switch
            id={OUTPUT_PLUGINS_SWITCH_ID}
            checked={settings.output_plugins_enabled}
            disabled={settingsMutation.isPending}
            onCheckedChange={(checked) => settingsMutation.mutate({ output_plugins_enabled: checked })}
            {...anchorProps("settings.plugins.output_plugins_enabled")}
          />
          <Label htmlFor={OUTPUT_PLUGINS_SWITCH_ID} className="text-sm font-normal">
            {t("outputPluginsLabel")}
          </Label>
        </Flex>
      )}
      <Button
        variant="outline"
        size="sm"
        onClick={() => checkMutation.mutate()}
        disabled={checkMutation.isPending}
        className="gap-2"
      >
        <RefreshCw className={cn("h-3.5 w-3.5", checkMutation.isPending && "animate-spin")} />
        {checkMutation.isPending ? t("checking") : t("checkForUpdates")}
      </Button>
    </Flex>
  );
}
