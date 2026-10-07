"use client";

/**
 * The install's plugin-update controls, split between the two places they
 * belong on the Integrations section:
 *
 * - `PluginUpdateCheckButton` — "Check for updates", the section header's one
 *   action (the same shape as Displays' "Add a display"). It acts on every
 *   plugin in the section.
 * - `PluginAutoUpdateSwitch` — the "Auto-update plugins" setting, on the
 *   Installed tab's toolbar row beside the plugins it governs. In the header
 *   it outweighed the section title and wrapped onto extra rows on a phone.
 *
 * Auto-update used to be a Settings card ("Plugin Updates"). The
 * `settings.plugins` anchors moved with the switch, so the AI walkthrough for
 * `update_setting(category="plugins")` still has something to point at on
 * /integrations — and never something tucked into the collapsed header on a
 * plugin's page. Display plugins need no switch: since settings v7 every one
 * can drive a board (Displays → Marketplace).
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

export function PluginUpdateCheckButton() {
  const t = useTranslations("integrations");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

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
  );
}

export function PluginAutoUpdateSwitch({ className }: { className?: string }) {
  const t = useTranslations("integrations");
  const { data: settings } = usePluginSettings();

  const settingsMutation = useUpdatePluginSettings({
    onSuccess: () => {
      toast.success(t("autoUpdateSavedToast"));
    },
    onError: (err: Error) => {
      toast.error(t("autoUpdateSaveFailedToast", { error: err.message }));
    },
  });

  // Hidden until the settings have loaded: a switch drawn "off" while the
  // request is in flight reads as a fact and invites a click that would save
  // the wrong value.
  if (!settings) return null;

  return (
    <Flex align="center" gap="2" className={cn("shrink-0", className)} {...anchorProps("settings.plugins")}>
      <Switch
        id={AUTO_UPDATE_SWITCH_ID}
        checked={settings.auto_update}
        disabled={settingsMutation.isPending}
        onCheckedChange={(checked) => settingsMutation.mutate({ auto_update: checked })}
        {...anchorProps("settings.plugins.auto_update")}
      />
      <Label htmlFor={AUTO_UPDATE_SWITCH_ID} className="whitespace-nowrap text-sm font-normal">
        {t("autoUpdateLabel")}
      </Label>
    </Flex>
  );
}
