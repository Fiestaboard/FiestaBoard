"use client";

/**
 * The install's plugin-update controls, split between the two places they
 * belong on the Integrations section:
 *
 * - `PluginUpdatesMenu` — the section header's "…" (07d `324:40267`), holding
 *   "Check for updates", which acts on every plugin in the section.
 *   `PluginUpdateCheckButton` is the same action as a labelled button, for
 *   the phone's updates block under the list.
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

import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Flex,
  Label,
  Switch,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { usePluginSettings, useUpdatePluginSettings } from "@/hooks/use-plugin-settings";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const AUTO_UPDATE_SWITCH_ID = "plugin-auto-update";

function usePluginUpdateCheck() {
  const t = useTranslations("integrations");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  return useMutation({
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
}

export function PluginUpdateCheckButton() {
  const t = useTranslations("integrations");
  const checkMutation = usePluginUpdateCheck();

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => checkMutation.mutate()}
      disabled={checkMutation.isPending}
      className="gap-2"
    >
      {checkMutation.isPending ? <Spinner size="sm" label={null} /> : <RefreshCw className="h-3.5 w-3.5" />}
      {checkMutation.isPending ? t("checking") : t("checkForUpdates")}
    </Button>
  );
}

/**
 * The section header's "…" (07d `324:40267`): Check for updates, which acts
 * on every plugin, behind one icon button rather than a labelled one.
 */
export function PluginUpdatesMenu() {
  const t = useTranslations("integrations");
  const checkMutation = usePluginUpdateCheck();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon" aria-label={t("moreOptionsAriaLabel")}>
          {checkMutation.isPending ? <Spinner size="sm" label={null} /> : <MoreHorizontal className="h-4 w-4" />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => checkMutation.mutate()} disabled={checkMutation.isPending}>
          <RefreshCw className="h-4 w-4 mr-2" aria-hidden="true" />
          {checkMutation.isPending ? t("checking") : t("checkForUpdates")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
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
