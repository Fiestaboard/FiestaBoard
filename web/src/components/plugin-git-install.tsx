"use client";

/**
 * Installing a plugin from a git repository URL (`POST /plugins/install`),
 * shared by Integrations → Marketplace ("Install Plugin from Git", a dialog)
 * and Displays → Marketplace ("Bring your own display", inline).
 *
 * `useGitPluginInstall` owns the three fields and the request, and refreshes
 * everything an install can change (plugins, the registry view, outputs,
 * template variables, previews). `GitInstallFields` renders the security
 * warning and the fields; each caller supplies its own Install button and
 * decides what to say on success or failure.
 */
import { Alert, AlertDescription, AlertTitle, Grid, Input, Label, Stack } from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useState } from "react";

import { OUTPUTS_QUERY_KEY } from "@/components/settings/output-boards";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

export interface GitPluginInstall {
  url: string;
  setUrl: (value: string) => void;
  pluginId: string;
  setPluginId: (value: string) => void;
  branch: string;
  setBranch: (value: string) => void;
  /** Whether there is a URL to install from. */
  canInstall: boolean;
  isInstalling: boolean;
  /** Install; resolves to the installed plugin's id, rejects with the server's error. */
  install: () => Promise<string>;
  /** Clear the fields. */
  reset: () => void;
}

export function useGitPluginInstall(): GitPluginInstall {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [pluginId, setPluginId] = useState("");
  const [branch, setBranch] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      const result = await api.installGitPlugin(url.trim(), pluginId.trim() || undefined, branch.trim() || undefined);
      return result.plugin_id;
    },
    onSuccess: async () => {
      await Promise.all(
        [["plugins"], ["plugin-registry"], ["template-variables"], ["plugin-displays-batch"], ["pagePreview"]].map(
          (queryKey) => queryClient.invalidateQueries({ queryKey }),
        ),
      );
      // Awaited: a caller asks "is it a display?" from these right after.
      await queryClient.invalidateQueries({ queryKey: OUTPUTS_QUERY_KEY });
    },
  });

  return {
    url,
    setUrl,
    pluginId,
    setPluginId,
    branch,
    setBranch,
    canInstall: url.trim().length > 0,
    isInstalling: mutation.isPending,
    install: () => mutation.mutateAsync(),
    reset: () => {
      setUrl("");
      setPluginId("");
      setBranch("");
    },
  };
}

/** The security warning and the URL / plugin id / branch fields. */
export function GitInstallFields({
  install,
  idPrefix,
  urlPlaceholder = "https://github.com/user/fiestaboard-plugin-example.git",
}: {
  install: GitPluginInstall;
  /** Keeps field ids unique when two forms are on one page. */
  idPrefix: string;
  urlPlaceholder?: string;
}) {
  const t = useTranslations("integrations");
  return (
    <Stack gap="4">
      {/* `variant="warning"`: the design system owns the recipe and the
          assertive role — external code is about to run on the device. */}
      <Alert variant="warning">
        <ShieldAlert className="h-4 w-4" />
        <AlertTitle>{t("securityWarningTitle")}</AlertTitle>
        <AlertDescription>{t("securityWarning")}</AlertDescription>
      </Alert>
      <Stack gap="2">
        <Label htmlFor={`${idPrefix}-url`}>{t("repoUrl")}</Label>
        <Input
          id={`${idPrefix}-url`}
          placeholder={urlPlaceholder}
          value={install.url}
          onChange={(e) => install.setUrl(e.target.value)}
          disabled={install.isInstalling}
        />
      </Stack>
      <Grid cols="2" gap="4">
        <Stack gap="2">
          <Label htmlFor={`${idPrefix}-plugin-id`}>{t("pluginIdOptional")}</Label>
          <Input
            id={`${idPrefix}-plugin-id`}
            placeholder={t("autoDetectedPlaceholder")}
            value={install.pluginId}
            onChange={(e) => install.setPluginId(e.target.value)}
            disabled={install.isInstalling}
          />
        </Stack>
        <Stack gap="2">
          <Label htmlFor={`${idPrefix}-branch`}>{t("branchOptional")}</Label>
          <Input
            id={`${idPrefix}-branch`}
            placeholder={t("defaultBranchPlaceholder")}
            value={install.branch}
            onChange={(e) => install.setBranch(e.target.value)}
            disabled={install.isInstalling}
          />
        </Stack>
      </Grid>
    </Stack>
  );
}
