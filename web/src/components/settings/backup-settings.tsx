"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Flex,
  Label,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Database, Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { useTranslations } from "@/i18n/translations";
import { api, ApiError } from "@/lib/api";

/** How long a downloaded backup's blob URL is kept before it is revoked. */
const BLOB_URL_LIFETIME_MS = 60_000;

interface PendingImport {
  fileName: string;
  payload: unknown;
}

export function BackupSettings() {
  const t = useTranslations("settings.backup");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [reinstallPlugins, setReinstallPlugins] = useState(true);
  const [pending, setPending] = useState<PendingImport | null>(null);

  const importMutation = useMutation({
    mutationFn: (vars: { payload: unknown; reinstallPlugins: boolean }) =>
      api.importBackup(vars.payload, vars.reinstallPlugins),
    onSuccess: (result) => {
      const restored = result.restored_files.length;
      const failed = result.plugins.failed.length;
      const installed = result.plugins.installed.length;
      const manualRequired = result.plugins.manual_reinstall_required ?? [];

      const parts = [t("restoredFiles", { count: restored })];
      if (installed > 0) parts.push(t("reinstalledPlugins", { count: installed }));
      if (failed > 0) parts.push(t("pluginsFailed", { count: failed }));
      toast.success(parts.join(" "));

      if (manualRequired.length > 0) {
        const names = manualRequired.map((p) => p.plugin_id).join(", ");
        toast.warning(t("manualReinstall", { count: manualRequired.length, names }), { duration: 8000 });
      }

      // Invalidate every query so the UI re-fetches the restored data.
      queryClient.invalidateQueries();
    },
    onError: (err: Error) => {
      toast.error(t("importFailed", { error: err.message }));
    },
  });

  // Fetch first, save second (BB-C-7): only a file the hub actually sent is
  // saved, and only then is success announced. An unreachable hub or an
  // error response says so and leaves the app where it is.
  const exportMutation = useMutation({
    mutationFn: () => api.exportBackup(),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // WebKit starts an anchor download asynchronously; revoking the URL
      // straight after the click can silently cancel it. Keep it a minute.
      setTimeout(() => URL.revokeObjectURL(url), BLOB_URL_LIFETIME_MS);
      toast.success(t("exportDone"));
    },
    onError: (err: Error) => {
      toast.error(err instanceof ApiError ? t("exportFailed", { error: err.message }) : t("exportUnreachable"));
    },
  });
  const busy = importMutation.isPending || exportMutation.isPending;

  const handleFileSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input so selecting the same file twice still fires onChange.
    event.target.value = "";
    if (!file) return;

    let text: string;
    try {
      text = await file.text();
    } catch (err) {
      toast.error(t("readFailed", { error: (err as Error).message }));
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      toast.error(t("invalidJson", { error: (err as Error).message }));
      return;
    }

    if (!parsed || typeof parsed !== "object" || !(parsed as Record<string, unknown>).fiestaboard_backup) {
      toast.error(t("notABackup"));
      return;
    }

    setPending({ fileName: file.name, payload: parsed });
  };

  const handleConfirmImport = () => {
    if (!pending) return;
    importMutation.mutate(
      { payload: pending.payload, reinstallPlugins },
      {
        onSettled: () => setPending(null),
      },
    );
  };

  return (
    <>
      <SettingsPanel
        icon={<Database />}
        title={t("cardTitle")}
        description={t("cardDescription")}
        contentClassName="space-y-6"
      >
        <Flex direction="col" gap="3" wrap className="sm:flex-row">
          <Button variant="default" className="gap-2" onClick={() => exportMutation.mutate()} disabled={busy}>
            {exportMutation.isPending ? <Spinner label={null} className="h-4 w-4" /> : <Download className="h-4 w-4" />}
            {t("exportButton")}
          </Button>
          <Button variant="outline" className="gap-2" onClick={() => fileInputRef.current?.click()} disabled={busy}>
            {importMutation.isPending ? <Spinner label={null} className="h-4 w-4" /> : <Upload className="h-4 w-4" />}
            {t("importButton")}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={handleFileSelected}
          />
        </Flex>

        <Flex align="start" gap="3" className="rounded-md border border-border/60 bg-muted/40 p-3">
          <Switch id="backup-reinstall-plugins" checked={reinstallPlugins} onCheckedChange={setReinstallPlugins} />
          <Stack gap="1">
            <Label htmlFor="backup-reinstall-plugins" className="cursor-pointer">
              {t("reinstallPluginsLabel")}
            </Label>
            <Text size="xs" tone="muted">
              {t("reinstallPluginsDescription")}
            </Text>
          </Stack>
        </Flex>

        <Text size="xs" tone="muted">
          {t("sensitiveNote")}
        </Text>
      </SettingsPanel>

      <AlertDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              {t("confirmTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t.rich("confirmDescription", {
                file: () => (
                  <Text as="span" weight="medium" tone="muted">
                    {pending?.fileName}
                  </Text>
                ),
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={importMutation.isPending}>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmImport} disabled={importMutation.isPending}>
              {importMutation.isPending ? (
                <>
                  <Spinner label={null} className="h-4 w-4 mr-2" />
                  {t("restoringButton")}
                </>
              ) : (
                t("restoreButton")
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
