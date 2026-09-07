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
  PageSection,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Database, Download, Loader2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

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

      let msg = `Restored ${restored} file${restored === 1 ? "" : "s"}.`;
      if (installed > 0) {
        msg += ` Reinstalled ${installed} plugin${installed === 1 ? "" : "s"}.`;
      }
      if (failed > 0) {
        msg += ` ${failed} plugin${failed === 1 ? "" : "s"} could not be reinstalled — install manually.`;
      }
      toast.success(msg);

      if (manualRequired.length > 0) {
        const names = manualRequired.map((p) => p.plugin_id).join(", ");
        toast.warning(
          `${manualRequired.length} external plugin${manualRequired.length === 1 ? "" : "s"} must be reinstalled manually via Integrations: ${names}`,
          { duration: 8000 },
        );
      }

      // Invalidate every query so the UI re-fetches the restored data.
      queryClient.invalidateQueries();
    },
    onError: (err: Error) => {
      toast.error(`Import failed: ${err.message}`);
    },
  });

  const handleExport = () => {
    // Trigger a file download via a temporary anchor element.  The
    // browser handles the Content-Disposition header from the server.
    const link = document.createElement("a");
    link.href = api.exportBackupUrl();
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Backup download started");
  };

  const handleFileSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input so selecting the same file twice still fires onChange.
    event.target.value = "";
    if (!file) return;

    let text: string;
    try {
      text = await file.text();
    } catch (err) {
      toast.error(`Could not read file: ${(err as Error).message}`);
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      toast.error(`File is not valid JSON: ${(err as Error).message}`);
      return;
    }

    if (!parsed || typeof parsed !== "object" || !(parsed as Record<string, unknown>).fiestaboard_backup) {
      toast.error("This does not look like a FiestaBoard backup file.");
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
      <PageSection
        icon={<Database />}
        title={t("cardTitle")}
        description={t("cardDescription")}
        contentClassName="space-y-6"
      >
        <Flex direction="col" gap="3" className="sm:flex-row">
          <Button variant="default" className="gap-2" onClick={handleExport} disabled={importMutation.isPending}>
            <Download className="h-4 w-4" />
            {t("exportButton")}
          </Button>
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => fileInputRef.current?.click()}
            disabled={importMutation.isPending}
          >
            {importMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
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
      </PageSection>

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
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
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
